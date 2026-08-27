"""The real runner, driven against a stubbed SDK.

Every other test uses `ScriptedRunner`, which meant `SDKRunner.invoke` had never
actually executed - and it carried a crash on its first line. These exercise the
real code path (message handling, rate-limit reading, option building) without a
live model call.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import claude_agent_sdk
import pytest

from shipyard.config import Settings
from shipyard.ledger import Ledger
from shipyard.runner import (
    MeteredRunner,
    RoleRequest,
    RoleResult,
    SDKRunner,
    UsageLimitReached,
)

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture()
def runner(tmp_path):
    settings = Settings(
        repo_root=REPO_ROOT,
        projects_dir=tmp_path / "projects",
        templates_dir=REPO_ROOT / "templates",
        prompts_dir=REPO_ROOT / "prompts",
    )
    project_dir = tmp_path / "projects" / "demo"
    project_dir.mkdir(parents=True)
    ledger = Ledger.create(project_dir, "demo", "Demo")
    return SDKRunner(ledger, settings), ledger, project_dir


def request_for(project_dir: Path) -> RoleRequest:
    return RoleRequest(
        role="analyst", task="research it", cwd=project_dir, stage="s10_research"
    )


def fake_query(messages):
    """Stand in for `claude_agent_sdk.query`, yielding canned messages."""

    async def _query(*, prompt, options, **kwargs):
        for message in messages:
            yield message

    return _query


def result_message(**kwargs):
    from claude_agent_sdk import ResultMessage

    defaults = dict(
        subtype="success", duration_ms=10, duration_api_ms=8, is_error=False,
        num_turns=1, session_id="s-1", total_cost_usd=0.25, usage={},
        result="done", terminal_reason="completed",
    )
    return ResultMessage(**{**defaults, **kwargs})


def rate_limit_message(status: str, utilization: dict[str, float] | None = None):
    from claude_agent_sdk import RateLimitEvent, RateLimitInfo

    windows = {k: {"utilization": v, "resetsAt": 1787872200} for k, v in (utilization or {}).items()}
    info = RateLimitInfo(
        status=status,
        resets_at=1787872200,
        rate_limit_type="five_hour",
        utilization=None,
        overage_status="allowed",
        overage_resets_at=None,
        overage_disabled_reason=None,
        raw={"status": status, "unifiedWindows": windows},
    )
    return RateLimitEvent(rate_limit_info=info, uuid="u-1", session_id="s-1")


# --------------------------------------------------------------------------


def test_a_role_result_can_be_built_the_way_the_runner_builds_it():
    """The crash that a real run found: `text` had no default."""
    assert RoleResult(role="analyst").text == ""


def test_the_runner_streams_a_session_into_a_result(runner, monkeypatch):
    sdk, ledger, project_dir = runner
    from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock

    monkeypatch.setattr(
        claude_agent_sdk,
        "query",
        fake_query(
            [
                AssistantMessage(
                    content=[TextBlock(text="found three competitors")],
                    model="claude-opus-5",
                ),
                AssistantMessage(
                    content=[ToolUseBlock(id="t1", name="WebFetch", input={})],
                    model="claude-opus-5",
                ),
                result_message(),
            ]
        ),
    )

    result = asyncio.run(sdk.invoke(request_for(project_dir)))

    assert "found three competitors" in result.text
    assert result.tool_calls == 1
    assert result.cost_usd == 0.25
    assert result.terminal_reason == "completed"
    assert not result.is_error and not result.rate_limited


def test_the_runner_reads_the_usage_window_off_the_stream(runner, monkeypatch):
    sdk, ledger, project_dir = runner
    monkeypatch.setattr(
        claude_agent_sdk,
        "query",
        fake_query(
            [
                rate_limit_message("allowed", {"five_hour": 0.2, "seven_day": 0.13}),
                result_message(),
            ]
        ),
    )

    result = asyncio.run(sdk.invoke(request_for(project_dir)))

    # The per-window numbers live under `raw`, not the top-level field.
    assert result.utilization == {"five_hour": 0.2, "seven_day": 0.13}
    assert result.rate_limit_window == "five_hour"
    assert result.resets_at == 1787872200
    assert not result.rate_limited


def test_a_rejected_window_marks_the_result_and_stops_the_run(runner, monkeypatch):
    sdk, ledger, project_dir = runner
    monkeypatch.setattr(
        claude_agent_sdk,
        "query",
        fake_query([rate_limit_message("rejected", {"five_hour": 1.0}), result_message()]),
    )

    metered = MeteredRunner(sdk, ledger)
    with pytest.raises(UsageLimitReached) as caught:
        asyncio.run(metered.invoke(request_for(project_dir)))

    assert caught.value.resets_at == 1787872200
    assert ledger.state.usage.status == "rejected"


def test_a_429_result_is_treated_as_a_usage_limit(runner, monkeypatch):
    sdk, ledger, project_dir = runner
    monkeypatch.setattr(
        claude_agent_sdk, "query", fake_query([result_message(is_error=True, api_error_status=429)])
    )

    with pytest.raises(UsageLimitReached):
        asyncio.run(MeteredRunner(sdk, ledger).invoke(request_for(project_dir)))


def test_an_sdk_exception_becomes_an_errored_result_not_a_crash(runner, monkeypatch):
    sdk, ledger, project_dir = runner

    async def explode(*, prompt, options, **kwargs):
        raise RuntimeError("connection reset")
        yield  # pragma: no cover

    monkeypatch.setattr(claude_agent_sdk, "query", explode)

    result = asyncio.run(sdk.invoke(request_for(project_dir)))

    assert result.is_error
    assert "connection reset" in result.terminal_reason


def test_the_options_never_carry_an_auth_variable(runner):
    """An empty auth var in `env` would shadow a working login."""
    sdk, _, project_dir = runner
    from shipyard.roles import get_role

    options = sdk._options(request_for(project_dir), get_role("analyst"), [])

    for key in options.env:
        assert "ANTHROPIC" not in key.upper()
        assert "TOKEN" not in key.upper()
        assert "KEY" not in key.upper()


def test_the_options_confine_writes_but_widen_reads(runner):
    sdk, _, project_dir = runner
    from shipyard.roles import get_role

    references = REPO_ROOT / "references"
    request = RoleRequest(
        role="ux_architect", task="t", cwd=project_dir, stage="s30_design",
        allowed_roots=[project_dir], read_roots=[references],
    )
    options = sdk._options(request, get_role("ux_architect"), [])

    assert options.cwd == str(project_dir)
    assert str(references) in options.add_dirs
    assert options.setting_sources == []
    # No ceiling unless one was asked for.
    assert options.max_budget_usd is None
    assert options.max_turns == get_role("ux_architect").max_turns
