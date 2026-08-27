"""Opportunity scouting: the survey that runs when nobody has chosen an idea."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fixtures as fx
import pytest
from pydantic import ValidationError

from shipyard.config import Settings
from shipyard.contracts import Shortlist
from shipyard.ledger import Ledger
from shipyard.runner import RoleRequest, ScriptedRunner
from shipyard.scout import (
    CAPABILITIES,
    build_shortlist_task,
    build_sweep_task,
    has_sweep,
    prepare,
    scout,
    sweep_path,
)

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture()
def workspace(tmp_path):
    settings = Settings(
        repo_root=REPO_ROOT,
        projects_dir=tmp_path / "projects",
        templates_dir=REPO_ROOT / "templates",
        prompts_dir=REPO_ROOT / "prompts",
        scouting_dir=tmp_path / "scouting",
    )
    directory, ledger = prepare(settings, "scout-test")
    return settings, directory, ledger


SWEEP_NOTES = "# Sweep\n\n" + ("A lead, its demand signal, and a URL. " * 40)


def two_phase_analyst(recommended: str = "Alpha", calls: list[str] | None = None):
    """Behaves like the real role: sweeps first, shortlists second."""

    def script(req: RoleRequest) -> str:
        if calls is not None:
            calls.append(req.task)
        if "first of two passes" in req.task:
            sweep_path(req.cwd).write_text(SWEEP_NOTES)
            return "swept the space"
        fx.shortlist(recommended).save(req.cwd)
        return "shortlisted the leads"

    return script


def test_a_scouting_pass_sweeps_then_shortlists(workspace):
    _, directory, ledger = workspace
    calls: list[str] = []
    runner = ScriptedRunner({"analyst": two_phase_analyst(calls=calls)})

    result = asyncio.run(scout(runner, ledger, directory, focus="", count=3))

    assert len(calls) == 2, "one call per phase"
    assert "first of two passes" in calls[0]
    assert "ranked shortlist" in calls[1]
    assert [c.rank for c in result.candidates] == [1, 2, 3]
    assert result.recommended == "Alpha"
    assert Shortlist.full_path(directory).is_file()
    assert has_sweep(directory), "the durable notes must survive the pass"


def test_a_second_run_resumes_from_the_sweep_instead_of_repeating_it(workspace):
    """The whole point of the split: a window that dies mid-pass costs the
    phase it was in, not the research already done."""
    _, directory, ledger = workspace
    sweep_path(directory).write_text(SWEEP_NOTES)
    calls: list[str] = []
    runner = ScriptedRunner({"analyst": two_phase_analyst(calls=calls)})

    asyncio.run(scout(runner, ledger, directory, count=3))

    assert len(calls) == 1, "the sweep should have been skipped"
    assert "ranked shortlist" in calls[0]


def test_the_shortlist_pass_is_given_the_sweep_to_work_from(workspace):
    _, directory, ledger = workspace
    calls: list[str] = []
    runner = ScriptedRunner({"analyst": two_phase_analyst(calls=calls)})

    asyncio.run(scout(runner, ledger, directory, count=3))

    assert str(sweep_path(directory)) in calls[1], "phase two must read phase one"


def test_notes_survive_a_pass_that_dies_after_the_sweep(workspace):
    """The case that motivated the split - twelve minutes of research lost
    because nothing had been written down."""
    _, directory, ledger = workspace
    from shipyard.runner import UsageLimitReached

    def dies_after_sweeping(req: RoleRequest) -> str:
        if "first of two passes" in req.task:
            sweep_path(req.cwd).write_text(SWEEP_NOTES)
            return "swept"
        raise UsageLimitReached("five_hour", 1787872200)

    runner = ScriptedRunner({"analyst": dies_after_sweeping})

    with pytest.raises(UsageLimitReached):
        asyncio.run(scout(runner, ledger, directory, count=3))

    assert has_sweep(directory), "the sweep must outlive the failed pass"
    assert not Shortlist.full_path(directory).is_file()


def test_a_sweep_that_wrote_nothing_usable_fails_loudly(workspace):
    _, directory, ledger = workspace

    def writes_a_stub(req: RoleRequest) -> str:
        sweep_path(req.cwd).write_text("# Sweep\n\nnothing yet")
        return "barely tried"

    runner = ScriptedRunner({"analyst": writes_a_stub})

    with pytest.raises(RuntimeError, match="no usable notes"):
        asyncio.run(scout(runner, ledger, directory, count=3))


def test_both_phases_state_what_the_studio_can_and_cannot_build(workspace):
    _, directory, _ = workspace
    for task in (
        build_sweep_task("offline utilities", 5, directory),
        build_shortlist_task("offline utilities", 5, directory),
    ):
        assert "offline utilities" in task
        assert CAPABILITIES in task
        # The constraints that actually disqualify a candidate must be explicit.
        for phrase in ("Two-sided marketplaces", "content licensing", "paid acquisition"):
            assert phrase in task


def test_the_sweep_is_told_to_write_as_it_goes(workspace):
    _, directory, _ = workspace
    task = build_sweep_task("timers", 5, directory)

    assert "incrementally, as you find them" in task
    assert str(sweep_path(directory)) in task
    # It should not be asked to reach a verdict in phase one.
    assert "Do not try to reach a final answer yet" in task


def test_the_shortlist_pass_demands_evidence_and_a_reject_pile(workspace):
    _, directory, _ = workspace
    task = build_shortlist_task("timers", 5, directory)

    assert "demand_evidence` must contain numbers" in task
    assert "also_considered" in task
    assert "leaving `recommended` empty is the right call" in task


def test_ranging_widely_is_asked_for_when_no_focus_is_given(workspace):
    _, directory, _ = workspace
    assert "Range widely" in build_sweep_task("", 5, directory)
    assert "Range widely" not in build_sweep_task("timers", 5, directory)


def test_recommending_nothing_is_a_valid_outcome(workspace):
    """The analyst already proved it will say no; the contract must let it."""
    _, directory, ledger = workspace
    runner = ScriptedRunner({"analyst": two_phase_analyst(recommended="")})

    result = asyncio.run(scout(runner, ledger, directory, count=3))

    assert result.recommended == ""
    assert result.pursue  # candidates can still be worth watching


def test_a_recommendation_must_name_a_candidate_it_believes_in():
    data = fx.shortlist().model_dump()
    data["recommended"] = "Something Else"
    with pytest.raises(ValidationError, match="not one of"):
        Shortlist.model_validate(data)

    # Recommending something it marked `watch` or `reject` is a contradiction.
    data = fx.shortlist().model_dump()
    data["recommended"] = "Beta"
    with pytest.raises(ValidationError, match="only a 'pursue' candidate"):
        Shortlist.model_validate(data)


def test_the_ranking_must_be_a_real_ranking():
    data = fx.shortlist().model_dump()
    data["candidates"][2]["rank"] = 1
    with pytest.raises(ValidationError, match="no gaps"):
        Shortlist.model_validate(data)

    data = fx.shortlist().model_dump()
    data["candidates"][1]["name"] = "Alpha"
    data["recommended"] = ""
    with pytest.raises(ValidationError, match="share a name"):
        Shortlist.model_validate(data)


def test_every_candidate_must_carry_evidence_and_competitors():
    data = fx.shortlist().model_dump()
    data["candidates"][0]["competitors"] = data["candidates"][0]["competitors"][:1]
    with pytest.raises(ValidationError, match="too_short"):
        Shortlist.model_validate(data)

    data = fx.shortlist().model_dump()
    data["candidates"][0]["sources"] = []
    with pytest.raises(ValidationError, match="too_short"):
        Shortlist.model_validate(data)


def test_the_pass_is_costed_like_any_other_role_call(workspace):
    _, directory, ledger = workspace
    runner = ScriptedRunner({"analyst": two_phase_analyst()}, cost_per_call=2.5)
    from shipyard.runner import MeteredRunner

    asyncio.run(scout(MeteredRunner(runner, ledger), ledger, directory, count=3))

    assert ledger.state.cost_usd == 5.0  # one call per phase
    assert any(r["role"] == "analyst" for r in ledger.cost_rows())
