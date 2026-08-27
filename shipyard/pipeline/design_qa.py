"""Stage 65: render the app, measure it, and look at it.

Up to here nothing in the pipeline has ever seen a screen. Typecheck, lint and
Jest all pass happily on an app that is ugly, cramped and unusable with a screen
reader, so this stage exports the app to web, drives it with a real browser at
phone viewports, photographs every route, and runs machine probes over what
rendered. Then a role that can actually see the images judges what a probe
cannot: hierarchy, rhythm, whether these screens look like one product.

Blocking findings become tickets and go through the same `TicketRunner` the
build loop uses, so a design fix cannot skip code review or leave trunk red.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import (
    AcceptanceCriterion,
    BuildReport,
    CopyDeck,
    DesignQAReport,
    Finding,
    Ticket,
    TicketOutcome,
    UISpec,
    UXSpec,
    coerce_verdict,
)
from ..runner import RoleRequest
from ..verify import Check, run_checks
from ..workspace import AppRepo
from . import Stage, StageContext
from .tickets import BuildConfig, TicketRunner, VERDICT_SHAPE

GALLERY_ROUTE = "/__gallery"


@dataclass
class DesignQAConfig:
    build: BuildConfig = field(default_factory=BuildConfig)
    #: `{out}` and `{routes}` are substituted. Tests stub this.
    screenshots_cmd: str = "node scripts/screenshots.mjs --out {out} --routes {routes}"
    timeout_s: int = 1800
    #: How many times findings may be turned into fixes before we stop.
    max_fix_rounds: int = 2


def web_route(route: str) -> str | None:
    """Turn an expo-router path into the URL the static web export serves.

    Route groups do not appear in URLs, and a dynamic segment cannot be rendered
    without data, so those routes are skipped rather than photographed blank.
    """
    if "[" in route:
        return None
    cleaned = re.sub(r"/\([^)]*\)", "", route)
    cleaned = re.sub(r"/index$", "/", cleaned)
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    cleaned = re.sub(r"//+", "/", cleaned)
    return cleaned


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


class DesignQA(Stage):
    key = "s65_design_qa"
    title = "Design QA"
    owner_role = "design_qa"
    requires = (UXSpec, UISpec, CopyDeck, BuildReport)
    outputs = (DesignQAReport,)
    dod = """
- Every screen in the UX spec that can be rendered was photographed.
- No serious or critical accessibility violation remains.
- No layout defect remains: no touch target under 44px, no clipped text, no
  horizontal overflow, no text below 12px.
- The screens look like one product: consistent spacing, a clear hierarchy, and
  a primary action that is obvious without reading every label.
""".strip()

    def __init__(self, config: DesignQAConfig | None = None) -> None:
        self.config = config or DesignQAConfig()

    # -- stage entry point -------------------------------------------------

    async def execute(self, ctx: StageContext) -> None:
        repo = AppRepo.open(ctx.app_dir)
        ux = UXSpec.load(ctx.project_dir)
        routes = self._routes(ux)
        qa_dir = ctx.project_dir / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)

        findings: list[Finding] = []
        fixes: list[TicketOutcome] = []
        report = self._capture(ctx, routes, qa_dir)
        summary = ""

        for round_ in range(1, self.config.max_fix_rounds + 1):
            mechanical = self._mechanical_findings(qa_dir)
            verdict = await self._look(ctx, routes, qa_dir, report.summary())
            findings = mechanical + verdict.findings
            summary = verdict.summary
            blocking = [f for f in findings if f.severity == "blocking"]
            if not blocking:
                break

            ctx.ledger.event(
                "design_qa.fixing", stage=self.key, round=round_, blocking=len(blocking)
            )
            fixes.extend(await self._fix(ctx, repo, blocking, round_))
            report = self._capture(ctx, routes, qa_dir)

        a11y = _read_json(qa_dir / "a11y.json", [])
        layout = _read_json(qa_dir / "layout.json", [])
        screens = sorted(
            str(p.relative_to(ctx.project_dir)) for p in (qa_dir / "screens").glob("*.png")
        )
        blocking = [f for f in findings if f.severity == "blocking"]

        DesignQAReport(
            routes=routes,
            screenshots=screens or ["(none captured)"],
            a11y_violations=len(a11y),
            layout_findings=len(layout),
            verdict="fail" if blocking else "pass",
            summary=summary or report.summary(),
            findings=findings,
            fixes=fixes,
        ).save(ctx.project_dir)

        if blocking:
            detail = "\n".join(f"- [{f.where}] {f.problem} -> {f.fix}" for f in blocking)
            raise RuntimeError(
                f"{len(blocking)} design defects survived "
                f"{self.config.max_fix_rounds} fix rounds:\n{detail}"
            )

    # -- capture -----------------------------------------------------------

    def _routes(self, ux: UXSpec) -> list[str]:
        routes = []
        for screen in ux.screens:
            route = web_route(screen.route)
            if route and route not in routes:
                routes.append(route)
        # The gallery renders every component in every state, so a regression in
        # a primitive is caught even when no screen happens to use it.
        routes.append(GALLERY_ROUTE)
        return routes

    def _capture(self, ctx: StageContext, routes: list[str], qa_dir: Path):
        command = self.config.screenshots_cmd.format(out=qa_dir, routes=",".join(routes))
        report = run_checks(
            [Check("screenshots", command, ctx.app_dir, self.config.timeout_s)],
            ctx.ledger,
            self.key,
        )
        failure = next((r for r in report.results if r.exit_code >= 2), None)
        if failure is not None:
            # Exit 2 means the run itself broke; that is not a design defect.
            raise RuntimeError("could not render the app for review:\n" + report.as_feedback())
        return report

    def _mechanical_findings(self, qa_dir: Path) -> list[Finding]:
        """Probe output as findings. These are measured, so they always block."""
        findings: list[Finding] = []
        for violation in _read_json(qa_dir / "a11y.json", []):
            if violation.get("impact") not in ("serious", "critical"):
                continue
            findings.append(
                Finding(
                    severity="blocking",
                    where=f"{violation.get('route', '?')} ({violation.get('id', 'a11y')})",
                    problem=violation.get("help", "accessibility violation"),
                    fix=(
                        "Fix the accessibility violation on this route. Offending "
                        "markup: " + "; ".join(violation.get("nodes", [])[:2])
                    ),
                )
            )
        for item in _read_json(qa_dir / "layout.json", []):
            findings.append(
                Finding(
                    severity="blocking",
                    where=f"{item.get('route', '?')} ({item.get('viewport', '?')})",
                    problem=f"{item.get('kind', 'layout')}: {item.get('detail', '')}",
                    fix=(
                        f"Adjust the component rendering {item.get('label') or 'this element'} "
                        f"so it no longer reports {item.get('kind')}."
                    ),
                )
            )
        return findings

    # -- the part that looks -----------------------------------------------

    async def _look(self, ctx: StageContext, routes: list[str], qa_dir: Path, checks: str):
        ui = UISpec.load(ctx.project_dir)
        ux = UXSpec.load(ctx.project_dir)
        shots = sorted((qa_dir / "screens").glob("*.png"))
        listing = "\n".join(f"- `{p}`" for p in shots) or "- (no screenshots were captured)"
        compositions = "\n".join(
            f"- **{c.screen_id}**: " + " → ".join(s.component for s in c.sections)
            for c in ui.screens
        )
        states = "\n".join(
            f"- {s.id}: " + ", ".join(st.name for st in s.states) for s in ux.screens
        )

        result = await ctx.runner.invoke(
            RoleRequest(
                role="design_qa",
                stage=self.key,
                cwd=ctx.project_dir,
                allowed_roots=[ctx.project_dir],
                task=f"""Judge whether **{ui.app_name}** is good enough to put in front of a user.

## Screenshots — read every one of these images before anything else

{listing}

Two viewports per route: `.iphone` is 390x844, `.android` is 360x800.

## What each screen was supposed to be

{compositions}

## States each screen can be in

{states}

## Machine checks already run

{checks}

The automated probes have already reported accessibility violations, touch
targets under 44px, clipped text, horizontal overflow and text below 12px. Do
not repeat them. Report what a machine cannot see: visual hierarchy, alignment
and rhythm, density, whether these screens look like one product, whether the
primary action is obvious, and whether anything looks like a placeholder.

{VERDICT_SHAPE}
""",
            )
        )
        verdict = coerce_verdict(result.structured, result.text)
        if verdict is None:
            ctx.ledger.event("design_qa.unparseable", stage=self.key)
            from ..contracts import Verdict

            return Verdict(
                verdict="pass",
                summary="the design reviewer returned nothing readable; the measured checks stand alone",
            )
        ctx.ledger.event(
            "design_qa.verdict",
            stage=self.key,
            verdict=verdict.verdict,
            blocking=len(verdict.blocking),
        )
        return verdict

    # -- repairs -----------------------------------------------------------

    async def _fix(
        self, ctx: StageContext, repo: AppRepo, blocking: list[Finding], round_: int
    ) -> list[TicketOutcome]:
        """Turn findings into tickets and run them through the build loop.

        Design fixes go through the same lifecycle as feature work - worktree,
        checks, review, serialized merge, trunk re-proof - so a cosmetic change
        cannot bypass the discipline the build stage established.
        """
        grouped: dict[str, list[Finding]] = {}
        for finding in blocking:
            grouped.setdefault(finding.where.split(" ")[0], []).append(finding)

        # One worker: these tickets all touch the UI layer, so running them in
        # parallel would mostly produce conflicts with each other.
        runner = TicketRunner(ctx, repo, self.config.build, self.key, concurrency=1)
        outcomes: list[TicketOutcome] = []

        for index, (where, group) in enumerate(sorted(grouped.items()), start=1):
            ticket_id = f"T-{900 + (round_ - 1) * 20 + index}"
            # Keep the full `where`: grouping is by route, but the rule id or
            # viewport that follows it is how an engineer reproduces the defect.
            detail = "\n".join(
                f"- [{f.where}] {f.problem}\n  Required fix: {f.fix}" for f in group
            )
            ticket = Ticket(
                id=ticket_id,
                title=f"Fix {len(group)} design defect(s) on {where}",
                description=f"Design QA found these on {where}:\n{detail}",
                # A design defect can live in any component the route renders.
                touches=["src/**"],
                requirement_ids=["design-qa"],
                acceptance=[
                    AcceptanceCriterion(
                        id=f"AC-{ticket_id}",
                        statement=(
                            f"Given {where}, when it is rendered and probed, then none of "
                            f"the reported defects appear."
                        ),
                        verified_by="e2e",
                    )
                ],
                estimate="s",
            )
            brief = f"""## Design QA fix — {where}

The app was rendered in a real browser and reviewed. These defects were found
and must be fixed:

{detail}

### How to fix them well

Change the component in `src/ui/` when the defect is in a primitive, so every
screen benefits. Change the screen only when the defect is in how that screen
composes existing components. Do not add a one-off style override to make one
screen pass.

Do not weaken the checks: the same probes run again after your change, and a
target that is still under 44px will simply come back.

Every visible string comes from `design/copy.json` via `t('key')` — do not
hardcode replacement copy.
"""
            outcome = await runner.run(ticket, brief, commit_type="fix")
            outcomes.append(outcome)
            ctx.ledger.event(
                "design_qa.fix",
                stage=self.key,
                ticket=ticket_id,
                where=where,
                status=outcome.status,
            )
        return outcomes


DESIGN_QA_STAGES: list[Stage] = [DesignQA()]
