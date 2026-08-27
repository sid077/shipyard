"""End-to-end orchestrator behaviour, with every role scripted.

These tests run the real pipeline - real contracts, real gates, real repair
loop, real check execution - without a single API call.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import replace
from pathlib import Path

import fixtures as fx
import pytest

from shipyard.config import Settings
from shipyard.contracts import MonetizationPlan, Opportunity
from shipyard.gates import Gate, decide
from shipyard.ledger import GateStatus, Ledger, StageStatus
from shipyard.pipeline import build_context, run_pipeline
from shipyard.pipeline.registry import STAGES
from shipyard.runner import RoleError, RoleRequest, ScriptedRunner, UsageLimitReached
from shipyard.workspace import create_project


def _write(artifact_fn, extra_files: dict[str, str] | None = None):
    """Build a script that writes an artifact the way a real role would."""

    def script(req: RoleRequest) -> str:
        artifact_fn().save(req.cwd)
        for rel, body in (extra_files or {}).items():
            path = Path(req.cwd) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return "wrote the artifact"

    return script


def happy_scripts() -> dict:
    return {
        "analyst": _write(fx.opportunity, {"research/research.md": "# Research\n\nFull write-up.\n"}),
        "monetization": _write(fx.monetization),
        "pm": _write(fx.prd, {"product/prd.md": "# PRD\n\nProse spec.\n"}),
        "ux_architect": _write(fx.ux),
        "ux_writer": _write(fx.copy_deck),
        "ui_designer": _write(fx.ui, {"design/preview.html": fx.preview_html()}),
        "architect": _write(fx.architecture),
        "planner": _write(fx.backlog),
        "critic": fx.PASS_VERDICT,
    }


@pytest.fixture()
def project(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        projects_dir=tmp_path / "projects",
        templates_dir=tmp_path / "templates",
        prompts_dir=Path(__file__).parent.parent / "prompts",
        max_repairs=2,
    )
    project_dir = create_project(settings.projects_dir, "tip-splitter")
    fx.idea().save(project_dir)
    ledger = Ledger.create(project_dir, "tip-splitter", "Tip Splitter")
    return settings, project_dir, ledger


def drive(settings, project_dir, ledger, scripts, cost=0.0, until="s50_planning"):
    """Run the pipeline. Stops after planning by default: the build loop has
    its own tests, and it needs npm."""
    runner = ScriptedRunner(scripts, cost_per_call=cost)
    ctx = build_context(project_dir, ledger, runner, settings)
    return asyncio.run(run_pipeline(STAGES, ctx, until=until)), runner


# --------------------------------------------------------------------------


def test_run_halts_at_g0_with_a_briefing(project):
    settings, project_dir, ledger = project
    outcome, runner = drive(settings, project_dir, ledger, happy_scripts())

    assert outcome.status == "awaiting_gate"
    assert outcome.gate == "G0"
    assert ledger.state.stage("s10_research").status == StageStatus.DONE
    # Nothing past the gate ran.
    assert ledger.state.stage("s20_definition").status == StageStatus.PENDING

    briefing = (project_dir / "inbox" / "G0.md").read_text()
    assert "Recommendation: **GO**" in briefing
    assert "Splitwise" in briefing          # real competitor data reached the operator
    assert "$2.99" in briefing              # so did the price
    assert "shipyard gate approve" in briefing


def test_approving_g0_continues_to_g1_then_completes(project):
    settings, project_dir, ledger = project
    scripts = happy_scripts()

    drive(settings, project_dir, ledger, scripts)
    decide(ledger, Gate.G0, True)
    outcome, _ = drive(settings, project_dir, ledger, scripts)
    assert outcome.gate == "G1"
    assert "Tip Splitter" in (project_dir / "inbox" / "G1.md").read_text()

    decide(ledger, Gate.G1, True)
    outcome, _ = drive(settings, project_dir, ledger, scripts)
    assert outcome.status == "complete"
    assert ledger.state.stage("s50_planning").status == StageStatus.DONE
    assert (project_dir / "backlog" / "tickets.json").is_file()


def test_resume_does_not_re_run_completed_stages(project):
    settings, project_dir, ledger = project
    scripts = happy_scripts()
    drive(settings, project_dir, ledger, scripts)
    decide(ledger, Gate.G0, True)

    _, runner = drive(settings, project_dir, ledger, scripts)
    roles_called = {c.role for c in runner.calls}
    assert "analyst" not in roles_called  # s10 was already done
    assert "pm" in roles_called


def test_rejecting_g1_re_runs_the_owning_stage_with_the_notes(project):
    settings, project_dir, ledger = project
    scripts = happy_scripts()
    drive(settings, project_dir, ledger, scripts)
    decide(ledger, Gate.G0, True)
    drive(settings, project_dir, ledger, scripts)

    decide(ledger, Gate.G1, False, notes="Drop the history screen; ship split-only.")
    outcome, runner = drive(settings, project_dir, ledger, scripts)

    pm_tasks = [c.task for c in runner.calls if c.role == "pm"]
    design_tasks = [c.task for c in runner.calls if c.role == "ux_architect"]
    assert pm_tasks and design_tasks, "both stages behind G1 must re-run"
    assert "Drop the history screen" in pm_tasks[0]
    assert "Drop the history screen" in design_tasks[0]
    # The gate is re-armed and asked again, not silently skipped.
    assert outcome.gate == "G1"
    assert ledger.state.gate("G1").status == GateStatus.PENDING


def test_invalid_artifact_triggers_a_repair_with_the_validation_error(project):
    settings, project_dir, ledger = project
    attempts = {"n": 0}

    def flaky_analyst(req: RoleRequest) -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            # Two competitors: violates min_length=3.
            bad = fx.opportunity()
            data = bad.model_dump(mode="json")
            data["competitors"] = data["competitors"][:2]
            path = Opportunity.full_path(req.cwd)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(__import__("json").dumps(data))
        else:
            fx.opportunity().save(req.cwd)
        (req.cwd / "research" / "research.md").write_text("# Research\n")
        return "done"

    scripts = happy_scripts() | {"analyst": flaky_analyst}
    outcome, runner = drive(settings, project_dir, ledger, scripts)

    assert outcome.status == "awaiting_gate"
    assert attempts["n"] == 2
    assert ledger.state.stage("s10_research").attempts == 2
    second_task = [c.task for c in runner.calls if c.role == "analyst"][1]
    # The stage aborts as soon as the bad artifact is read, before the next
    # role wastes a call on it, and the pydantic error is handed back verbatim.
    assert "does not satisfy its contract" in second_task
    assert "competitors" in second_task


def test_stage_blocks_after_max_repairs_and_writes_an_inbox_briefing(project):
    settings, project_dir, ledger = project

    def always_bad(req: RoleRequest) -> str:
        (req.cwd / "research").mkdir(parents=True, exist_ok=True)
        Opportunity.full_path(req.cwd).write_text('{"problem": "incomplete"}')
        return "done"

    outcome, _ = drive(settings, project_dir, ledger, happy_scripts() | {"analyst": always_bad})

    assert outcome.status == "blocked"
    assert outcome.stage == "s10_research"
    assert ledger.state.stage("s10_research").attempts == settings.max_repairs + 1
    assert (project_dir / "inbox" / "BLOCKED-s10_research.md").is_file()


def test_failing_check_triggers_a_repair_with_the_command_output(project):
    settings, project_dir, ledger = project
    attempts = {"n": 0}

    def analyst(req: RoleRequest) -> str:
        attempts["n"] += 1
        fx.opportunity().save(req.cwd)
        if attempts["n"] > 1:  # forgot the prose write-up the first time
            (req.cwd / "research" / "research.md").write_text("# Research\n")
        return "done"

    outcome, runner = drive(settings, project_dir, ledger, happy_scripts() | {"analyst": analyst})

    assert outcome.status == "awaiting_gate"
    assert attempts["n"] == 2
    assert "Verification commands failed" in [c.task for c in runner.calls if c.role == "analyst"][1]


def test_critic_blocking_finding_triggers_a_repair(project):
    settings, project_dir, ledger = project
    verdicts = iter([
        '{"verdict":"fail","summary":"pricing is invented",'
        '"findings":[{"severity":"blocking","where":"monetization.json",'
        '"problem":"price has no competitor basis","fix":"cite a real competitor price"}]}',
    ])

    def critic(req: RoleRequest) -> str:
        return next(verdicts, fx.PASS_VERDICT)

    outcome, runner = drive(settings, project_dir, ledger, happy_scripts() | {"critic": critic})

    assert outcome.status == "awaiting_gate"
    analyst_tasks = [c.task for c in runner.calls if c.role == "analyst"]
    assert len(analyst_tasks) == 2
    assert "cite a real competitor price" in analyst_tasks[1]


def test_a_fail_verdict_with_no_blocking_finding_is_not_a_fail(project):
    settings, project_dir, ledger = project
    soft = '{"verdict":"fail","summary":"nits","findings":[{"severity":"advisory","where":"x","problem":"y","fix":"z"}]}'
    outcome, runner = drive(settings, project_dir, ledger, happy_scripts() | {"critic": soft})

    assert outcome.status == "awaiting_gate"
    assert len([c for c in runner.calls if c.role == "analyst"]) == 1


def test_unparseable_critic_is_skipped_rather_than_deadlocking(project):
    settings, project_dir, ledger = project
    outcome, runner = drive(settings, project_dir, ledger, happy_scripts() | {"critic": "I could not decide."})

    assert outcome.status == "awaiting_gate"
    # Two attempts to parse, then the machine checks stand alone.
    assert len([c for c in runner.calls if c.role == "critic"]) == 2


def test_project_budget_halts_the_run(project):
    settings, project_dir, ledger = project
    settings = replace(settings, project_budget_usd=1.0)
    outcome, _ = drive(settings, project_dir, ledger, happy_scripts(), cost=0.6)

    assert outcome.status == "budget_exceeded"
    assert ledger.state.cost_usd >= 1.0


def test_missing_input_artifact_blocks_instead_of_calling_a_role(project):
    settings, project_dir, ledger = project
    # Mark research done without producing its artifacts.
    ledger.stage_done("s00_intake")
    ledger.stage_done("s10_research")
    decide(ledger, Gate.G0, True)

    outcome, runner = drive(settings, project_dir, ledger, happy_scripts())

    assert outcome.status == "blocked"
    assert outcome.stage == "s20_definition"
    assert "missing input artifact" in outcome.message
    assert not [c for c in runner.calls if c.role == "pm"]


def test_state_survives_a_fresh_ledger_open(project):
    settings, project_dir, ledger = project
    drive(settings, project_dir, ledger, happy_scripts())

    reopened = Ledger.open(project_dir)
    assert reopened.state.stage("s10_research").status == StageStatus.DONE
    assert reopened.state.gate("G0").status == GateStatus.PENDING
    assert MonetizationPlan.load(project_dir).model == "one_time"


# --------------------------------------------------------------------------
# Spend ceilings, usage windows, and errors that used to vanish
# --------------------------------------------------------------------------


def test_no_ceiling_is_set_by_default(project):
    """The account's usage window is the real limit; a dollar estimate is not."""
    settings, project_dir, ledger = project
    assert Settings().project_budget_usd is None
    assert Settings().stage_budget_usd is None

    outcome, _ = drive(settings, project_dir, ledger, happy_scripts(), cost=500.0)

    assert outcome.status == "awaiting_gate", "an unset ceiling must never halt a run"
    assert ledger.state.cost_usd >= 500.0


def test_an_explicit_ceiling_still_halts(project):
    settings, project_dir, ledger = project
    settings = replace(settings, project_budget_usd=1.0)

    outcome, _ = drive(settings, project_dir, ledger, happy_scripts(), cost=0.6)

    assert outcome.status == "budget_exceeded"


def test_a_metered_runner_raises_rather_than_swallowing_a_failure():
    """The bug this replaces: an errored role produced nothing, failed the
    artifact contract, and burned every repair attempt on an unfixable cause."""
    from shipyard.runner import MeteredRunner, RoleResult, UsageLimitReached

    class Stub:
        def __init__(self, result):
            self.result = result

        async def invoke(self, req):
            return self.result

    ledger = Ledger.create(Path(tempfile.mkdtemp()) / "p", "demo", "Demo")
    request = RoleRequest(role="analyst", task="t", cwd=Path("."), stage="s10_research")

    limited = RoleResult(
        role="analyst", text="", rate_limited=True,
        rate_limit_window="five_hour", resets_at=1787872200,
        utilization={"five_hour": 1.0},
    )
    with pytest.raises(UsageLimitReached) as caught:
        asyncio.run(MeteredRunner(Stub(limited), ledger).invoke(request))
    assert caught.value.resets_at == 1787872200
    assert "five_hour" in str(caught.value)
    # The window is recorded on state, so `status` can report it after the fact.
    assert ledger.state.usage.status == "rejected"
    assert ledger.state.usage.utilization == {"five_hour": 1.0}

    errored = RoleResult(role="analyst", text="", is_error=True, terminal_reason="api_error 500")
    with pytest.raises(RoleError, match="api_error 500"):
        asyncio.run(MeteredRunner(Stub(errored), ledger).invoke(request))


def test_a_usage_limit_pauses_the_run_without_spending_a_repair_attempt(project):
    settings, project_dir, ledger = project

    def exhausted(req: RoleRequest) -> str:
        raise UsageLimitReached("five_hour", 1787872200)

    outcome, _ = drive(settings, project_dir, ledger, happy_scripts() | {"analyst": exhausted})

    assert outcome.status == "limit_reached"
    assert outcome.resets_at == 1787872200
    assert outcome.resumable, "a paused run must resume, not restart"
    assert "shipyard resume" in outcome.message

    # The stage is left ready to run again, with its attempt given back.
    record = ledger.state.stage("s10_research")
    assert record.status == StageStatus.PENDING
    assert record.attempts == 0
    assert ledger.state.stage("s10_research").note == ""


def test_a_paused_run_carries_on_from_where_it_stopped(project):
    settings, project_dir, ledger = project
    calls = {"n": 0}

    def flaky(req: RoleRequest) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise UsageLimitReached("five_hour", 1787872200)
        return _write(fx.opportunity, {"research/research.md": "# Research\n"})(req)

    scripts = happy_scripts() | {"analyst": flaky}
    outcome, _ = drive(settings, project_dir, ledger, scripts)
    assert outcome.status == "limit_reached"

    # Nothing was lost: the window reopens and the same command carries on.
    outcome, _ = drive(settings, project_dir, ledger, scripts)
    assert outcome.status == "awaiting_gate"
    assert outcome.gate == "G0"
    assert ledger.state.stage("s10_research").attempts == 1


def test_an_api_error_is_handed_back_as_repairable_feedback(project):
    settings, project_dir, ledger = project
    attempts = {"n": 0}

    def flaky(req: RoleRequest) -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RoleError("analyst", "api_error 529 overloaded")
        return _write(fx.opportunity, {"research/research.md": "# Research\n"})(req)

    outcome, runner = drive(settings, project_dir, ledger, happy_scripts() | {"analyst": flaky})

    assert outcome.status == "awaiting_gate"
    assert attempts["n"] == 2
    second = [c.task for c in runner.calls if c.role == "analyst"][1]
    assert "529 overloaded" in second, "the role should see why its last attempt died"


def test_auto_approving_a_gate_records_that_no_human_read_it(project):
    settings, project_dir, ledger = project
    runner = ScriptedRunner(happy_scripts())
    ctx = build_context(project_dir, ledger, runner, settings)
    ctx.auto_approve = frozenset({"G0"})

    outcome = asyncio.run(run_pipeline(STAGES, ctx, until="s50_planning"))

    assert outcome.gate == "G1", "only G0 was auto-approved"
    g0 = ledger.state.gate("G0")
    assert g0.status == GateStatus.APPROVED
    assert g0.decided_by == "machine"
    assert "auto-approve" in g0.notes
    # G1 still waits for a person.
    assert ledger.state.gate("G1").status == GateStatus.PENDING


def test_each_completed_stage_can_be_checkpointed(project):
    settings, project_dir, ledger = project
    checkpointed: list[str] = []
    runner = ScriptedRunner(happy_scripts())
    ctx = build_context(project_dir, ledger, runner, settings)
    ctx.on_stage_done = checkpointed.append

    asyncio.run(run_pipeline(STAGES, ctx, until="s50_planning"))

    assert checkpointed == ["s00_intake", "s10_research"], "one hook per completed stage"
