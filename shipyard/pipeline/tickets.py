"""One ticket, from an empty worktree to a merged, still-green trunk.

Extracted from the build loop so any stage that needs code changed can reuse
exactly the same discipline: an isolated worktree, checks that must pass, a
review that must not block, a serialized merge, and a trunk that is re-proved
after every one of them. Design QA runs its fixes through this too, which is
why a design fix cannot bypass code review or leave trunk red.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import Finding, Ticket, TicketOutcome, Verdict, coerce_verdict
from ..ledger import TicketStatus
from ..runner import RoleRequest
from ..verify import Check, app_checks, run_checks
from ..workspace import AppRepo
from . import StageContext

MAX_DIFF_CHARS = 60_000

VERDICT_SHAPE = """Reply with a single JSON object and nothing else:

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


@dataclass
class BuildConfig:
    """Everything the ticket lifecycle shells out to, in one injectable place.

    Tests substitute fast no-op commands here, which is what lets the whole loop
    - worktrees, merges, reverts, repair rounds - be covered without npm.
    """

    install_cmd: str = "npm ci"
    checks: Callable[[Path], list[Check]] = field(default=app_checks)
    max_ticket_repairs: int = 3
    max_integration_attempts: int = 2
    concurrency: int | None = None
    install_timeout_s: int = 1800


def truncate(text: str, limit: int = MAX_DIFF_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...(diff truncated at {limit} characters)..."


def review_task(ticket: Ticket, diff: str, changed: list[str]) -> str:
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

{VERDICT_SHAPE}
"""


def security_task(ticket: Ticket, diff: str, changed: list[str]) -> str:
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

{VERDICT_SHAPE}
"""


class TicketRunner:
    """Runs tickets against one app repository, with merges serialized."""

    def __init__(
        self,
        ctx: StageContext,
        repo: AppRepo,
        config: BuildConfig,
        stage: str,
        concurrency: int | None = None,
    ) -> None:
        self.ctx = ctx
        self.repo = repo
        self.config = config
        self.stage = stage
        limit = concurrency or config.concurrency or ctx.settings.build_concurrency
        self.concurrency = max(limit, 1)
        self.merge_lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(self.concurrency)

    # -- one ticket --------------------------------------------------------

    async def run(self, ticket: Ticket, brief: str, commit_type: str = "feat") -> TicketOutcome:
        ctx, repo = self.ctx, self.repo
        async with self.semaphore:
            ctx.ledger.state.tickets[ticket.id] = TicketStatus.IN_PROGRESS
            ctx.ledger.save()
            ctx.ledger.event("ticket.started", stage=self.stage, ticket=ticket.id)

            worktree = repo.add_worktree(ticket.id)
            repo.link_dependencies(ticket.id)

            feedback = ctx.feedback
            attempts = 0
            blocking = 0

            for attempt in range(1, self.config.max_ticket_repairs + 2):
                attempts = attempt
                await self.invoke_dev(worktree, self.dev_task(brief, feedback))
                commit = repo.commit_worktree(
                    ticket.id, f"{commit_type}({ticket.id}): {ticket.title}"
                )

                if commit is None and attempt == 1:
                    feedback = (
                        "You changed no files. Implement the ticket: read the acceptance "
                        "criteria above, then write the code and the tests they call for."
                    )
                    continue

                report = run_checks(self.config.checks(worktree), ctx.ledger, self.stage)
                if not report.ok:
                    feedback = (
                        "The checks failed on your change. Fix the cause; do not weaken "
                        "the check.\n\n" + report.as_feedback()
                    )
                    continue

                verdict = await self.review(ticket, worktree)
                if verdict.verdict == "fail":
                    blocking = len(verdict.blocking)
                    feedback = verdict.as_feedback()
                    continue

                return await self.integrate(ticket, brief, attempts, blocking, commit_type)

            ctx.ledger.event(
                "ticket.blocked", stage=self.stage, ticket=ticket.id, reason="repairs exhausted"
            )
            return TicketOutcome(
                id=ticket.id,
                status="blocked",
                attempts=attempts,
                blocking_findings=blocking,
                note=f"failed {attempts} attempts; last problem:\n{feedback[:1500]}",
            )

    async def invoke_dev(self, worktree: Path, task: str) -> None:
        await self.ctx.runner.invoke(
            RoleRequest(
                role="dev",
                stage=self.stage,
                task=task,
                cwd=worktree,
                allowed_roots=[worktree],
                read_roots=[self.ctx.project_dir],
            )
        )

    def dev_task(self, brief: str, feedback: str) -> str:
        if not feedback.strip():
            return brief
        return (
            brief
            + "\n\n## You are being re-run\n\nYour previous attempt was not accepted. "
            "Address this in full; the ticket itself is unchanged.\n\n"
            + feedback.strip()
            + "\n"
        )

    # -- review ------------------------------------------------------------

    async def review(self, ticket: Ticket, worktree: Path) -> Verdict:
        ctx, repo = self.ctx, self.repo
        diff = truncate(repo.worktree_diff(ticket.id))
        changed = repo.worktree_changed_files(ticket.id)
        findings: list[Finding] = []
        summaries: list[str] = []

        reviews: list[tuple[str, str]] = [("reviewer", review_task(ticket, diff, changed))]
        if ticket.sensitive:
            reviews.append(("security", security_task(ticket, diff, changed)))

        for role, task in reviews:
            result = await ctx.runner.invoke(
                RoleRequest(
                    role=role,
                    stage=self.stage,
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
                    "review.unparseable", stage=self.stage, ticket=ticket.id, role=role
                )
                continue
            ctx.ledger.event(
                "review.verdict",
                stage=self.stage,
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

    async def integrate(
        self,
        ticket: Ticket,
        brief: str,
        attempts: int,
        blocking: int,
        commit_type: str = "feat",
    ) -> TicketOutcome:
        """Merge into trunk and prove trunk still passes, or put it back."""
        ctx, repo = self.ctx, self.repo
        last = ""
        for round_ in range(1, self.config.max_integration_attempts + 1):
            async with self.merge_lock:
                merge = repo.merge_ticket(ticket.id)
                if merge.ok:
                    trunk = run_checks(self.config.checks(repo.root), ctx.ledger, self.stage)
                    if trunk.ok:
                        head = repo.git.head()
                        repo.remove_worktree(ticket.id, delete_branch=False)
                        ctx.ledger.event(
                            "ticket.merged", stage=self.stage, ticket=ticket.id, commit=head
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
                        "ticket.reverted", stage=self.stage, ticket=ticket.id, round=round_
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
                        stage=self.stage,
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
            await self.invoke_dev(repo.worktree_path(ticket.id), self.dev_task(brief, fix))
            repo.commit_worktree(ticket.id, f"fix({ticket.id}): integrate with trunk")
            report = run_checks(
                self.config.checks(repo.worktree_path(ticket.id)), ctx.ledger, self.stage
            )
            if not report.ok:
                last = report.as_feedback()

        ctx.ledger.event(
            "ticket.blocked", stage=self.stage, ticket=ticket.id, reason="integration failed"
        )
        return TicketOutcome(
            id=ticket.id,
            status="blocked",
            attempts=attempts,
            integration_attempts=self.config.max_integration_attempts,
            blocking_findings=blocking,
            note=f"could not integrate with trunk:\n{last[:1500]}",
        )


def scaffold_app(ctx: StageContext, config: BuildConfig, stage: str) -> AppRepo:
    """Create the app from the template and apply the product config.

    Idempotent: a re-run opens the existing repository rather than starting the
    product over.
    """
    app_dir = ctx.app_dir
    if (app_dir / ".git").exists():
        repo = AppRepo.open(app_dir)
    else:
        template = ctx.settings.templates_dir / "expo-app"
        repo = AppRepo.from_template(template, app_dir)
        ctx.ledger.event("build.scaffolded", stage=stage, template=str(template))

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
        stage,
    )
    if not applied.ok:
        raise RuntimeError("could not apply the product config:\n" + applied.as_feedback())

    if not (app_dir / "node_modules").exists():
        installed = run_checks(
            [Check("install", config.install_cmd, app_dir, config.install_timeout_s)],
            ctx.ledger,
            stage,
        )
        if not installed.ok:
            raise RuntimeError("dependency install failed:\n" + installed.as_feedback())

    if repo.git.is_dirty():
        repo.git.commit_all("chore: apply product configuration")

    # If the scaffold is not green, no ticket can be. Fail here, where the cause
    # is obvious, rather than blaming the first engineer.
    baseline = run_checks(config.checks(app_dir), ctx.ledger, stage)
    if not baseline.ok:
        raise RuntimeError(
            "the scaffolded app does not pass its own checks before any ticket "
            "has been written:\n" + baseline.as_feedback()
        )
    return repo
