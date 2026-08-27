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
from shipyard.scout import CAPABILITIES, build_task, prepare, scout

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


def writes_shortlist(recommended: str = "Alpha"):
    def script(req: RoleRequest) -> str:
        fx.shortlist(recommended).save(req.cwd)
        return "surveyed the space"

    return script


def test_a_scouting_pass_produces_a_ranked_shortlist(workspace):
    _, directory, ledger = workspace
    runner = ScriptedRunner({"analyst": writes_shortlist()})

    result = asyncio.run(scout(runner, ledger, directory, focus="", count=3))

    assert [c.rank for c in result.candidates] == [1, 2, 3]
    assert result.recommended == "Alpha"
    assert [c.name for c in result.pursue] == ["Alpha"]
    assert Shortlist.full_path(directory).is_file()


def test_the_task_states_what_the_studio_can_and_cannot_build(workspace):
    _, directory, _ = workspace
    task = build_task("offline utilities", 5, directory)

    assert "offline utilities" in task
    assert "cannot do" in CAPABILITIES and CAPABILITIES in task
    # The constraints that actually disqualify a candidate must be explicit.
    for phrase in ("Two-sided marketplaces", "content licensing", "paid acquisition"):
        assert phrase in task
    assert "demand_evidence` must contain numbers" in task


def test_ranging_widely_is_asked_for_when_no_focus_is_given(workspace):
    _, directory, _ = workspace
    assert "Range widely" in build_task("", 5, directory)
    assert "Range widely" not in build_task("timers", 5, directory)


def test_recommending_nothing_is_a_valid_outcome(workspace):
    """The analyst already proved it will say no; the contract must let it."""
    _, directory, ledger = workspace
    runner = ScriptedRunner({"analyst": writes_shortlist(recommended="")})

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
    runner = ScriptedRunner({"analyst": writes_shortlist()}, cost_per_call=2.5)
    from shipyard.runner import MeteredRunner

    asyncio.run(scout(MeteredRunner(runner, ledger), ledger, directory, count=3))

    assert ledger.state.cost_usd == 2.5
    assert any(r["role"] == "analyst" for r in ledger.cost_rows())
