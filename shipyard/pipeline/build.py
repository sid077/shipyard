"""Stage 60: the build loop.

Engineers work in parallel, each in an isolated git worktree; the orchestrator
owns integration. That split is the whole design:

* a `dev` role edits files and nothing else - it never branches, commits or
  merges, because a botched merge costs far more to recover from than a botched
  function;
* merges are serialized behind a lock and every merge is proved on trunk before
  it stands, so a ticket that breaks the build is reverted rather than inherited
  by the next one;
* a merge conflict is handed back as a code task, with trunk already merged into
  the worktree and the markers live, which is a job agents are good at.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import (
    Architecture,
    Backlog,
    BuildReport,
    CopyDeck,
    Idea,
    MonetizationPlan,
    PRD,
    Ticket,
    UISpec,
    UXSpec,
    TicketOutcome,
    Verdict,
    coerce_verdict,
)
from ..ledger import TicketStatus
from ..runner import RoleRequest
from ..verify import Check, CheckReport, app_checks, run_checks
from ..workspace import AppRepo
from . import Stage, StageContext

MAX_DIFF_CHARS = 60_000


@dataclass
class BuildConfig:
    """Everything the build loop shells out to, in one injectable place.

    Tests substitute fast no-op commands here, which is what lets the whole loop
    - worktrees, merges, reverts, repair rounds - be covered without npm.
    """

    install_cmd: str = "npm ci"
    checks: Callable[[Path], list[Check]] = field(default=app_checks)
    max_ticket_repairs: int = 3
    max_integration_attempts: int = 2
    concurrency: int | None = None
    install_timeout_s: int = 1800


def _truncate(text: str, limit: int = MAX_DIFF_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(diff truncated at {limit} characters)..."


class Build(Stage):
    key = "s60_build"
    title = "Build"
    owner_role = "dev"
    requires = (Idea, PRD, UXSpec, UISpec, CopyDeck, Architecture, Backlog, MonetizationPlan)
    outputs = (BuildReport,)
    dod = """
- Every ticket in the backlog reached `merged`.
- The trunk commit named in the report is the head of a tree that passed the
  full check suite after the last merge.
- No check was weakened to reach green: no new `any`, no `eslint-disable`
  without a justifying comment, no skipped or deleted tests.
- Paid features are gated with `useEntitlement` on feature keys that exist in
  `monetization.json`, not on booleans or local flags.
""".strip()

    def __init__(self, config: BuildConfig | None = None) -> None:
        self.config = config or BuildConfig()

    # -- stage entry point -------------------------------------------------

    async def execute(self, ctx: StageContext) -> None:
        repo = self._scaffold(ctx)
        backlog = Backlog.load(ctx.project_dir)
        state = ctx.ledger.state

        # A previous attempt's blocked tickets get a genuine second chance;
        # merged ones are never redone.
        for ticket in backlog.tickets:
            if state.tickets.get(ticket.id) != TicketStatus.MERGED:
                state.tickets[ticket.id] = TicketStatus.PENDING
        ctx.ledger.save()

        # Tickets that landed on an earlier attempt still belong in the report,
        # otherwise a resumed stage has nothing to say about them.
        outcomes: dict[str, TicketOutcome] = {
            t.id: TicketOutcome(
                id=t.id, status="merged", attempts=0, note="merged on an earlier attempt"
            )
            for t in backlog.tickets
            if state.tickets.get(t.id) == TicketStatus.MERGED
        }
        merge_lock = asyncio.Lock()
        concurrency = self.config.concurrency or ctx.settings.build_concurrency
        semaphore = asyncio.Semaphore(max(concurrency, 1))

        done = {t.id for t in backlog.tickets if state.tickets.get(t.id) == TicketStatus.MERGED}
        failed: set[str] = set()

        while True:
            ready = [t for t in backlog.ready(done) if t.id not in failed]
            if not ready:
                break
            wave = ready[: max(concurrency, 1)]
            ctx.ledger.event(
                "build.wave", stage=self.key, tickets=[t.id for t in wave], done=len(done)
            )
            results = await asyncio.gather(
                *(self._run_ticket(ctx, repo, t, merge_lock, semaphore) for t in wave)
            )
            for outcome in results:
                outcomes[outcome.id] = outcome
                if outcome.status == "merged":
                    done.add(outcome.id)
                    ctx.ledger.state.tickets[outcome.id] = TicketStatus.MERGED
                else:
                    failed.add(outcome.id)
                    ctx.ledger.state.tickets[outcome.id] = TicketStatus.BLOCKED
            ctx.ledger.save()

        # Anything still unstarted was waiting on a ticket that never landed.
        for ticket in backlog.tickets:
            if ticket.id in outcomes or ticket.id in done:
                continue
            unmet = [d for d in ticket.depends_on if d not in done]
            outcomes[ticket.id] = TicketOutcome(
                id=ticket.id,
                status="blocked",
                attempts=0,
                note=f"never started; waiting on {', '.join(unmet)}",
            )
            ctx.ledger.state.tickets[ticket.id] = TicketStatus.BLOCKED
        ctx.ledger.save()

        trunk_report = run_checks(self.config.checks(repo.root), ctx.ledger, self.key)
        BuildReport(
            trunk_commit=repo.git.head(),
            tickets=[outcomes[t.id] for t in backlog.tickets],
            checks=trunk_report.summary(),
        ).save(ctx.project_dir)

        blocked = [o for o in outcomes.values() if o.status == "blocked"]
        if blocked:
            detail = "\n".join(f"- {o.id}: {o.note}" for o in blocked)
            raise RuntimeError(
                f"{len(blocked)} of {len(backlog.tickets)} tickets did not land:\n{detail}"
            )
        if not trunk_report.ok:
            raise RuntimeError(
                "every ticket merged but trunk is not green:\n" + trunk_report.as_feedback()
            )

    def checks(self, ctx: StageContext) -> list[Check]:
        # The trunk suite already ran inside `execute`, on the tree that the
        # report names. Re-running it here would only duplicate the cost.
        return []

    # -- scaffolding -------------------------------------------------------

    def _scaffold(self, ctx: StageContext) -> AppRepo:
        """Create the app from the template and apply the product config.

        Idempotent: a re-run of the stage opens the existing repository rather
        than starting the product over.
        """
        app_dir = ctx.app_dir
        if (app_dir / ".git").exists():
            repo = AppRepo.open(app_dir)
        else:
            template = ctx.settings.templates_dir / "expo-app"
            repo = AppRepo.from_template(template, app_dir)
            ctx.ledger.event("build.scaffolded", stage=self.key, template=str(template))

        applied = run_checks(
            [
                Check(
                    "apply-product",
                    f"node scripts/apply-product.mjs --project {ctx.project_dir}",
                    app_dir,
                    300,
                )
            ],
            ctx.ledger,
            self.key,
        )
        if not applied.ok:
            raise RuntimeError("could not apply the product config:\n" + applied.as_feedback())

        if not (app_dir / "node_modules").exists():
            installed = run_checks(
                [Check("install", self.config.install_cmd, app_dir, self.config.install_timeout_s)],
                ctx.ledger,
                self.key,
            )
            if not installed.ok:
                raise RuntimeError("dependency install failed:\n" + installed.as_feedback())

        if repo.git.is_dirty():
            repo.git.commit_all("chore: apply product configuration")

        # If the scaffold is not green, no ticket can be. Fail here, where the
        # cause is obvious, rather than blaming the first engineer.
        baseline = run_checks(self.config.checks(app_dir), ctx.ledger, self.key)
        if not baseline.ok:
            raise RuntimeError(
                "the scaffolded app does not pass its own checks before any ticket "
                "has been written:\n" + baseline.as_feedback()
            )
        return repo

    # -- one ticket --------------------------------------------------------

    async def _run_ticket(
        self,
        ctx: StageContext,
        repo: AppRepo,
        ticket: Ticket,
        merge_lock: asyncio.Lock,
        semaphore: asyncio.Semaphore,
    ) -> TicketOutcome:
        async with semaphore:
            ctx.ledger.state.tickets[ticket.id] = TicketStatus.IN_PROGRESS
            ctx.ledger.save()
            ctx.ledger.event("ticket.started", stage=self.key, ticket=ticket.id)

            worktree = repo.add_worktree(ticket.id)
            repo.link_dependencies(ticket.id)

            brief = self._ticket_brief(ctx, ticket)
            feedback = ctx.feedback
            attempts = 0
            blocking = 0

            for attempt in range(1, self.config.max_ticket_repairs + 2):
                attempts = attempt
                await self._invoke_dev(ctx, worktree, self._dev_task(brief, feedback))
                commit = repo.commit_worktree(ticket.id, f"feat({ticket.id}): {ticket.title}")

                if commit is None and attempt == 1:
                    feedback = (
                        "You changed no files. Implement the ticket: read the acceptance "
                        "criteria above, then write the code and the tests they call for."
                    )
                    continue

                report = run_checks(self.config.checks(worktree), ctx.ledger, self.key)
                if not report.ok:
                    feedback = (
                        "The checks failed on your change. Fix the cause; do not weaken "
                        "the check.\n\n" + report.as_feedback()
                    )
                    continue

                verdict = await self._review(ctx, repo, ticket, worktree)
                if verdict.verdict == "fail":
                    blocking = len(verdict.blocking)
                    feedback = verdict.as_feedback()
                    continue

                return await self._integrate(
                    ctx, repo, ticket, brief, attempts, blocking, merge_lock
                )

            ctx.ledger.event(
                "ticket.blocked", stage=self.key, ticket=ticket.id, reason="repairs exhausted"
            )
            return TicketOutcome(
                id=ticket.id,
                status="blocked",
                attempts=attempts,
                blocking_findings=blocking,
                note=f"failed {attempts} attempts; last problem:\n{feedback[:1500]}",
            )

    async def _invoke_dev(self, ctx: StageContext, worktree: Path, task: str) -> None:
        await ctx.runner.invoke(
            RoleRequest(
                role="dev",
                stage=self.key,
                task=task,
                cwd=worktree,
                allowed_roots=[worktree],
                read_roots=[ctx.project_dir],
            )
        )

    # -- review ------------------------------------------------------------

    async def _review(
        self, ctx: StageContext, repo: AppRepo, ticket: Ticket, worktree: Path
    ) -> Verdict:
        diff = _truncate(repo.worktree_diff(ticket.id))
        changed = repo.worktree_changed_files(ticket.id)
        findings: list = []
        summaries: list[str] = []

        reviews: list[tuple[str, str]] = [("reviewer", self._review_task(ticket, diff, changed))]
        if ticket.sensitive:
            reviews.append(("security", self._security_task(ticket, diff, changed)))

        for role, task in reviews:
            result = await ctx.runner.invoke(
                RoleRequest(
                    role=role,
                    stage=self.key,
                    task=task,
                    cwd=worktree,
                    allowed_roots=[worktree],
                    read_roots=[ctx.project_dir],
                )
            )
            verdict = coerce_verdict(result.structured, result.text)
            if verdict is None:
                # A reviewer that cannot answer must not silently approve, but
                # it must not deadlock the ticket either: the machine checks
                # have already passed, so record it and move on.
                ctx.ledger.event(
                    "review.unparseable", stage=self.key, ticket=ticket.id, role=role
                )
                continue
            ctx.ledger.event(
                "review.verdict",
                stage=self.key,
                ticket=ticket.id,
                role=role,
                verdict=verdict.verdict,
                blocking=len(verdict.blocking),
            )
            findings.extend(verdict.findings)
            summaries.append(f"{role}: {verdict.summary}")

        blocking = [f for f in findings if f.severity == "blocking"]
        return Verdict(
            verdict="fail" if blocking else "pass",
            summary="; ".join(summaries) or "no reviewer returned a verdict",
            findings=findings,
        )

    # -- integration -------------------------------------------------------

    async def _integrate(
        self,
        ctx: StageContext,
        repo: AppRepo,
        ticket: Ticket,
        brief: str,
        attempts: int,
        blocking: int,
        merge_lock: asyncio.Lock,
    ) -> TicketOutcome:
        """Merge into trunk and prove trunk still passes, or put it back."""
        last = ""
        for round_ in range(1, self.config.max_integration_attempts + 1):
            async with merge_lock:
                merge = repo.merge_ticket(ticket.id)
                if merge.ok:
                    trunk = run_checks(self.config.checks(repo.root), ctx.ledger, self.key)
                    if trunk.ok:
                        head = repo.git.head()
                        repo.remove_worktree(ticket.id, delete_branch=False)
                        ctx.ledger.event(
                            "ticket.merged", stage=self.key, ticket=ticket.id, commit=head
                        )
                        return TicketOutcome(
                            id=ticket.id,
                            status="merged",
                            attempts=attempts,
                            integration_attempts=round_,
                            blocking_findings=blocking,
                            commit=head,
                        )
                    # Trunk must never stay red on someone else's behalf.
                    repo.revert_last_merge()
                    repo.merge_trunk_into_worktree(ticket.id)
                    last = trunk.as_feedback()
                    ctx.ledger.event(
                        "ticket.reverted", stage=self.key, ticket=ticket.id, round=round_
                    )
                    fix = (
                        "Your change passed on its own but broke the build once merged "
                        "with everyone else's work. Trunk has been merged into your "
                        "worktree; fix the integration failure there.\n\n" + last
                    )
                else:
                    last = "merge conflict in: " + ", ".join(merge.conflicts)
                    ctx.ledger.event(
                        "ticket.conflict",
                        stage=self.key,
                        ticket=ticket.id,
                        files=merge.conflicts,
                    )
                    fix = (
                        "Trunk moved under you and your change now conflicts. Trunk has "
                        "been merged into your worktree and the conflict markers are "
                        "live in these files: "
                        + ", ".join(merge.conflicts)
                        + ".\n\nResolve them by keeping both behaviours. Deleting the "
                        "other engineer's work to make the markers go away is not a "
                        "resolution."
                    )

            # The repair runs outside the lock so other tickets keep moving.
            await self._invoke_dev(ctx, repo.worktree_path(ticket.id), self._dev_task(brief, fix))
            repo.commit_worktree(ticket.id, f"fix({ticket.id}): integrate with trunk")
            report = run_checks(
                self.config.checks(repo.worktree_path(ticket.id)), ctx.ledger, self.key
            )
            if not report.ok:
                last = report.as_feedback()

        ctx.ledger.event(
            "ticket.blocked", stage=self.key, ticket=ticket.id, reason="integration failed"
        )
        return TicketOutcome(
            id=ticket.id,
            status="blocked",
            attempts=attempts,
            integration_attempts=self.config.max_integration_attempts,
            blocking_findings=blocking,
            note=f"could not integrate with trunk:\n{last[:1500]}",
        )

    # -- prompts -----------------------------------------------------------

    def _ticket_brief(self, ctx: StageContext, ticket: Ticket) -> str:
        prd = PRD.load(ctx.project_dir)
        ux = UXSpec.load(ctx.project_dir)
        ui = UISpec.load(ctx.project_dir)
        copy = CopyDeck.load(ctx.project_dir)
        arch = Architecture.load(ctx.project_dir)
        monetization = MonetizationPlan.load(ctx.project_dir)

        wanted = {r.id for r in prd.requirements} & set(ticket.requirement_ids)
        requirements = "\n\n".join(
            f"**{r.id} - {r.title}** ({r.priority})\n{r.description}\n"
            + "\n".join(f"- [{a.verified_by}] {a.statement}" for a in r.acceptance)
            for r in prd.requirements
            if r.id in wanted
        )
        acceptance = "\n".join(
            f"- [{a.verified_by}] {a.statement}" for a in ticket.acceptance
        )
        screens = "\n".join(
            f"| `{s.id}` | `{s.route}` | {s.purpose} | "
            f"{s.requires_entitlement or '-'} | {', '.join(st.name for st in s.states)} |"
            for s in ux.screens
        )
        states = "\n".join(
            f"- **{s.id} / {st.name}** - {st.trigger}: renders {st.renders}"
            + (f' (copy `{st.copy_key}`: "{copy.entries[st.copy_key].text}")'
               if st.copy_key and st.copy_key in copy.entries else "")
            for s in ux.screens
            for st in s.states
        )
        components = "\n".join(
            f"- `{c.name}` - {c.purpose}; variants {', '.join(c.variants)}; "
            f"states {', '.join(c.states)}"
            for c in ui.components
        )
        compositions = "\n".join(
            f"- **{sc.screen_id}**: "
            + " → ".join(
                f"{sec.component}"
                + (f'("{copy.entries[sec.copy_key].text}")'
                   if sec.copy_key and sec.copy_key in copy.entries else "")
                for sec in sc.sections
            )
            for sc in ui.screens
        )
        transitions = "\n".join(
            f"- `{t.name}` - {t.describes}: {t.duration_ms}ms, {t.easing}"
            for t in ux.transitions
        )
        modules = "\n".join(f"- `{m.path}` - {m.responsibility}" for m in arch.modules)
        feature_keys = sorted({f for fs in monetization.entitlements.values() for f in fs})

        loading = ux.loading_strategy
        return f"""## Ticket {ticket.id}: {ticket.title}

{ticket.description}

### Acceptance criteria - this ticket is not done until these hold

{acceptance}

### Requirements it serves

{requirements or '(none recorded)'}

### Files you may change

{chr(10).join(f'- `{glob}`' for glob in ticket.touches)}

Anything outside these globs is another engineer's work in progress. Changing
it causes a merge conflict that costs the team a cycle.

### Screens in this app

| Screen | Route | Purpose | Entitlement | States |
|---|---|---|---|---|
{screens}

### Every state these screens can be in

{states}

A state you do not build is a bug that ships. Build the empty, loading and error
states listed above, not only the default one.

### The component inventory — compose from this, do not invent

{components}

Import from `@/ui`. If a screen genuinely needs something the inventory lacks,
add it to `src/ui/` as a reusable component with the same API shape as its
neighbours — never as a one-off inside a screen.

### Screen compositions

{compositions}

### Motion

{transitions}

Loading strategy: {loading}. Honour "Reduce Motion".

### Copy

Every visible string comes from `design/copy.json`. Do not invent copy, and do
not hardcode a string the deck already defines.

### Modules

{modules}

### Entitlement feature keys

{', '.join(f'`{k}`' for k in feature_keys)}

Gate paid features with `useEntitlement('<key>')` using exactly these keys.
Never gate on a boolean or a local flag.

### How your work is checked

`npm run typecheck`, `npm run lint`, `npm run format:check` and `npm run test`
all run against your worktree before the change is reviewed. Run them yourself
and fix what they report.
"""

    def _dev_task(self, brief: str, feedback: str) -> str:
        if not feedback.strip():
            return brief
        return (
            brief
            + "\n\n## You are being re-run\n\nYour previous attempt was not accepted. "
            "Address this in full; the ticket itself is unchanged.\n\n"
            + feedback.strip()
            + "\n"
        )

    def _review_task(self, ticket: Ticket, diff: str, changed: list[str]) -> str:
        return f"""Review this change against its ticket and decide whether it may land.

## Ticket {ticket.id}: {ticket.title}

{ticket.description}

### Acceptance criteria

{chr(10).join(f'- [{a.verified_by}] {a.statement}' for a in ticket.acceptance)}

### The ticket was allowed to change

{chr(10).join(f'- `{g}`' for g in ticket.touches)}

### Files actually changed

{chr(10).join(f'- `{f}`' for f in changed) or '- (none)'}

### Diff

```diff
{diff}
```

Typecheck, lint, formatting and the unit tests already pass - do not re-report
what they would catch. Read the files around the diff if you need context.

{_VERDICT_SHAPE}
"""

    def _security_task(self, ticket: Ticket, diff: str, changed: list[str]) -> str:
        return f"""This change touches authentication, purchases, entitlements or persisted
user data. Review it for anything that would harm a user or get the app
rejected from a store.

## Ticket {ticket.id}: {ticket.title}

{ticket.description}

### Files changed

{chr(10).join(f'- `{f}`' for f in changed) or '- (none)'}

### Diff

```diff
{diff}
```

Pay particular attention to: entitlement state read from the store rather than
a local flag; secrets that must not ship in a client build; session tokens in
secure storage; row-level security on any table holding user data; and whether
what the code collects matches what the privacy declarations say.

{_VERDICT_SHAPE}
"""


_VERDICT_SHAPE = """Reply with a single JSON object and nothing else:

{
  "verdict": "pass" | "fail",
  "summary": "one sentence",
  "findings": [
    {"severity": "blocking" | "advisory",
     "where": "path:line",
     "problem": "what goes wrong",
     "fix": "the specific change that resolves it"}
  ]
}

Return "fail" only when at least one finding is "blocking"."""



BUILD_STAGES: list[Stage] = [Build()]
