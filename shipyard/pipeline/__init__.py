"""The orchestrator.

Deterministic Python decides what happens next. Roles are stateless workers that
read typed artifacts and write typed artifacts; they never choose the next step,
never own git, and never declare their own work finished.

Every stage ends the same way:

1. the owning role produces artifacts,
2. those artifacts must validate against their contract,
3. the stage's checks must exit zero,
4. the critic must not raise a blocking finding.

Failing any of 2-4 re-invokes the role with the failure text attached, up to
`settings.max_repairs`. After that the stage is marked blocked and a briefing
lands in `inbox/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .. import gates
from ..config import Settings, load_settings
from ..contracts import Artifact
from ..critic import audit
from ..gates import GATE_OWNER_STAGE, Gate
from ..ledger import GateStatus, Ledger, StageStatus
from ..runner import MeteredRunner, Runner
from ..verify import Check, CheckReport, run_checks


@dataclass
class StageContext:
    settings: Settings
    ledger: Ledger
    runner: Runner
    project_dir: Path
    #: Feedback carried into the current attempt (critic, checks, or operator).
    feedback: str = ""

    @property
    def app_dir(self) -> Path:
        return self.project_dir / "app"

    @property
    def slug(self) -> str:
        return self.ledger.state.slug

    def load(self, cls: type[Artifact]):
        return cls.load(self.project_dir)


class Stage(ABC):
    """One step of the pipeline."""

    key: str
    title: str
    owner_role: str
    #: Artifacts this stage must produce, validated after every attempt.
    outputs: tuple[type[Artifact], ...] = ()
    #: Artifacts that must already exist before this stage may run.
    requires: tuple[type[Artifact], ...] = ()
    gate_after: Gate | None = None
    dod: str = ""
    #: Stages that produce nothing a critic could judge skip the audit.
    audit: bool = True

    @abstractmethod
    async def execute(self, ctx: StageContext) -> None:
        """Do the role work. Raise on unrecoverable failure."""

    def checks(self, ctx: StageContext) -> list[Check]:
        return []

    def briefing(self, ctx: StageContext) -> str:
        """Markdown shown to the operator when this stage raises a gate."""
        return f"Stage `{self.key}` completed."

    # -- helpers used by the runner loop ----------------------------------

    def output_paths(self, ctx: StageContext) -> list[Path]:
        return [cls.full_path(ctx.project_dir) for cls in self.outputs]

    def validate_outputs(self, ctx: StageContext) -> list[str]:
        problems: list[str] = []
        for cls in self.outputs:
            path = cls.full_path(ctx.project_dir)
            if not path.is_file():
                problems.append(f"missing required artifact: {cls.rel_path}")
                continue
            try:
                cls.load(ctx.project_dir)
            except Exception as exc:
                problems.append(
                    f"{cls.rel_path} does not satisfy its contract:\n{exc}"
                )
        return problems

    def check_requires(self, ctx: StageContext) -> list[str]:
        return [
            f"missing input artifact {cls.rel_path} (an earlier stage must produce it)"
            for cls in self.requires
            if not cls.exists(ctx.project_dir)
        ]


Status = Literal["complete", "awaiting_gate", "blocked", "budget_exceeded"]


@dataclass
class PipelineOutcome:
    status: Status
    message: str
    stage: str | None = None
    gate: str | None = None
    stages_run: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("complete", "awaiting_gate")


async def run_stage(stage: Stage, ctx: StageContext) -> tuple[bool, str]:
    """Run one stage through its repair loop. Returns (succeeded, message)."""
    ledger = ctx.ledger
    settings = ctx.settings
    max_attempts = settings.max_repairs + 1
    last_problem = "unknown"

    missing = stage.check_requires(ctx)
    if missing:
        return False, "; ".join(missing)

    for attempt in range(1, max_attempts + 1):
        ledger.stage_started(stage.key)
        try:
            await stage.execute(ctx)
        except Exception as exc:
            last_problem = f"stage raised {type(exc).__name__}: {exc}"
            ledger.event("stage.exception", stage=stage.key, error=last_problem)
            ctx.feedback = (
                "The stage aborted before finishing. Produce the required output "
                "again, correcting this:\n\n" + str(exc)
            )
            continue

        problems = stage.validate_outputs(ctx)
        if problems:
            last_problem = "\n".join(problems)
            ledger.event("stage.contract_failed", stage=stage.key, attempt=attempt)
            ctx.feedback = (
                "Your previous output did not satisfy the artifact contract. "
                "Fix exactly these problems and rewrite the file(s):\n\n" + last_problem
            )
            continue

        report: CheckReport = run_checks(stage.checks(ctx), ledger, stage.key)
        if not report.ok:
            last_problem = report.as_feedback()
            ledger.event("stage.checks_failed", stage=stage.key, attempt=attempt)
            ctx.feedback = (
                "Verification commands failed. Fix the cause, do not weaken the "
                "check:\n\n" + last_problem
            )
            continue

        if stage.audit:
            verdict = await audit(
                ctx.runner,
                ledger,
                stage=stage.key,
                project_dir=ctx.project_dir,
                dod=stage.dod or f"Stage {stage.key} produced its declared artifacts.",
                artifacts=stage.output_paths(ctx),
                checks=report,
            )
            if verdict.verdict == "fail":
                last_problem = verdict.as_feedback()
                ctx.feedback = last_problem
                continue

        ctx.feedback = ""
        ledger.stage_done(stage.key, report.summary())
        return True, report.summary()

    return False, last_problem


def _over_budget(ledger: Ledger, settings: Settings) -> str:
    """Return a reason the run must stop on spend, or an empty string."""
    if ledger.state.cost_usd < settings.project_budget_usd:
        return ""
    return (
        f"project budget of ${settings.project_budget_usd:.2f} reached "
        f"(spent ${ledger.state.cost_usd:.2f})"
    )


async def run_pipeline(
    stages: list[Stage],
    ctx: StageContext,
    *,
    until: str | None = None,
) -> PipelineOutcome:
    ledger = ctx.ledger
    settings = ctx.settings
    ran: list[str] = []
    #: Operator notes that must reach every stage between a rejected gate's
    #: owning stage and the gate itself.
    pending_notes: dict[str, str] = {}

    index = 0
    while index < len(stages):
        stage = stages[index]
        record = ledger.state.stage(stage.key)

        over = _over_budget(ledger, settings)
        if over:
            ledger.stage_blocked(stage.key, over)
            return PipelineOutcome("budget_exceeded", over, stage.key, stages_run=ran)

        if record.status != StageStatus.DONE:
            ctx.feedback = pending_notes.get(stage.key, "")
            ok, message = await run_stage(stage, ctx)
            if not ok:
                ledger.stage_blocked(stage.key, message)
                ledger.write_inbox(
                    f"BLOCKED-{stage.key}.md",
                    f"# Blocked: {stage.title}\n\n"
                    f"Stage `{stage.key}` failed {settings.max_repairs + 1} attempts.\n\n"
                    f"## Last failure\n\n```\n{message}\n```\n\n"
                    f"Fix the underlying issue, then run "
                    f"`shipyard resume {ledger.state.slug}`.\n",
                )
                return PipelineOutcome("blocked", message, stage.key, stages_run=ran)
            ran.append(stage.key)
            pending_notes.pop(stage.key, None)
            over = _over_budget(ledger, settings)
            if over:
                return PipelineOutcome("budget_exceeded", over, stage.key, stages_run=ran)

        if stage.gate_after is not None:
            gate = stage.gate_after
            state = gates.status(ledger, gate)
            if state == GateStatus.REJECTED:
                notes = gates.feedback(ledger, gate)
                owner = GATE_OWNER_STAGE[gate]
                owner_index = next(
                    (i for i, s in enumerate(stages) if s.key == owner), index
                )
                for s in stages[owner_index : index + 1]:
                    ledger.state.stage(s.key).status = StageStatus.PENDING
                    pending_notes[s.key] = notes
                gates.clear_rejection(ledger, gate)
                ledger.save()
                ledger.event("gate.rerun", gate=gate.value, from_stage=owner)
                index = owner_index
                continue
            if state != GateStatus.APPROVED:
                gates.request(ledger, gate, stage.briefing(ctx))
                title = gates.GATE_INFO[gate][0]
                return PipelineOutcome(
                    "awaiting_gate",
                    f"gate {gate.value} ({title}) is waiting for you: "
                    f"see {ledger.inbox / (gate.value + '.md')}",
                    stage.key,
                    gate.value,
                    ran,
                )

        if until and stage.key == until:
            return PipelineOutcome(
                "complete", f"stopped after {stage.key} as requested", stage.key, stages_run=ran
            )
        index += 1

    ledger.state.current_stage = None
    ledger.save()
    return PipelineOutcome("complete", "all stages complete", stages_run=ran)


def build_context(
    project_dir: Path, ledger: Ledger, runner: Runner, settings: Settings | None = None
) -> StageContext:
    return StageContext(
        settings=settings or load_settings(),
        ledger=ledger,
        # Every runner is metered, so the project budget holds regardless of
        # which implementation the caller supplied.
        runner=runner if isinstance(runner, MeteredRunner) else MeteredRunner(runner, ledger),
        project_dir=Path(project_dir),
    )
