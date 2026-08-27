"""The single place the Claude Agent SDK is called.

Every role invocation in the org funnels through `Runner.invoke`. That is what
makes spend bounded, tool access least-privilege, and the whole pipeline
testable: swap `SDKRunner` for `ScriptedRunner` and the orchestrator runs end to
end with no API calls.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .config import Settings, load_settings
from .guards import make_guard
from .ledger import Ledger
from .roles import RoleSpec, get_role


class RoleError(RuntimeError):
    """A role invocation failed for a reason the role might recover from."""

    def __init__(self, role: str, reason: str) -> None:
        super().__init__(f"role {role!r} failed: {reason}")
        self.role = role
        self.reason = reason


class UsageLimitReached(RuntimeError):
    """The account's rate-limit window is exhausted.

    Not a role failure and not repairable: retrying only wastes attempts. The
    pipeline checkpoints and stops so the run can resume once the window resets.
    """

    def __init__(self, window: str | None, resets_at: int | None) -> None:
        self.window = window or "usage"
        self.resets_at = resets_at
        when = ""
        if resets_at:
            from datetime import datetime, timezone

            stamp = datetime.fromtimestamp(resets_at, timezone.utc)
            when = f", resets {stamp.strftime('%H:%M UTC on %d %b')}"
        super().__init__(f"the {self.window} usage window is exhausted{when}")


@dataclass
class RoleRequest:
    role: str
    task: str
    cwd: Path
    stage: str
    #: Directories this role may write to. Defaults to `[cwd]`.
    allowed_roots: list[Path] = field(default_factory=list)
    #: Directories the role may read but must not write. Used by the build loop
    #: so a `dev` confined to one worktree can still read the specification.
    read_roots: list[Path] = field(default_factory=list)
    resume: str | None = None
    budget_usd: float | None = None
    extra_tools: list[str] = field(default_factory=list)

    def roots(self) -> list[Path]:
        return self.allowed_roots or [self.cwd]


@dataclass
class RoleResult:
    role: str
    #: Accumulated as the session streams, so it starts empty.
    text: str = ""
    cost_usd: float = 0.0
    session_id: str | None = None
    terminal_reason: str = "unknown"
    is_error: bool = False
    tool_calls: int = 0
    denials: list[str] = field(default_factory=list)
    structured: Any = None
    #: Set when the account's usage window was exhausted during this call.
    rate_limited: bool = False
    rate_limit_window: str | None = None
    resets_at: int | None = None
    #: Per-window utilization, 0.0-1.0, as last reported by the CLI.
    utilization: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.is_error


class Runner(Protocol):
    async def invoke(self, req: RoleRequest) -> RoleResult: ...


class SDKRunner:
    """Runs a role as a real Claude Agent SDK session."""

    def __init__(self, ledger: Ledger, settings: Settings | None = None) -> None:
        self.ledger = ledger
        self.settings = settings or load_settings()

    def _record_rate_limit(self, result: RoleResult, info: Any, stage: str = "") -> None:
        _record_rate_limit_impl(result, info, self.ledger, stage)

    def _system_prompt(self, spec: RoleSpec) -> str:
        path = spec.prompt_path(self.settings)
        if not path.is_file():
            raise FileNotFoundError(
                f"role {spec.name!r} has no system prompt at {path}"
            )
        return path.read_text(encoding="utf-8")

    def _options(self, req: RoleRequest, spec: RoleSpec, denials: list[str]) -> Any:
        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

        roots = req.roots()
        # The guard allows writes only to `roots`; `read_roots` widen what the
        # session can see, not what it can change.
        guard = make_guard(roots, on_deny=lambda tool, why: denials.append(f"{tool}: {why}"))
        tools = list(dict.fromkeys([*spec.tools, *req.extra_tools]))
        visible = [*roots, *req.read_roots]
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(spec),
            model=spec.model,
            effort=spec.effort,
            thinking={"type": "adaptive"},
            allowed_tools=tools,
            disallowed_tools=spec.disallowed,
            permission_mode="acceptEdits",
            cwd=str(req.cwd),
            add_dirs=[str(r) for r in visible if Path(r) != Path(req.cwd)],
            max_turns=spec.max_turns,
            # `max_turns` stays: it bounds a confused role, which is a different
            # risk from spend. A dollar ceiling is applied only when one is
            # explicitly configured - see `Settings.project_budget_usd`.
            max_budget_usd=req.budget_usd,
            # Hermetic: no user/project settings, CLAUDE.md or plugins leak in.
            setting_sources=[],
            # Merged into the inherited environment by the Python SDK, never
            # replacing it - which is how a role subprocess picks up whatever
            # credentials this process was started with. Never put an auth
            # variable in here: an empty one would shadow a working login.
            env={
                "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
                "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "4",
            },
            hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]},
            resume=req.resume,
            fork_session=bool(req.resume),
        )

    async def invoke(self, req: RoleRequest) -> RoleResult:
        from claude_agent_sdk import (
            AssistantMessage,
            RateLimitEvent,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
            query,
        )

        spec = get_role(req.role)
        denials: list[str] = []
        options = self._options(req, spec, denials)

        chunks: list[str] = []
        result = RoleResult(role=req.role)
        saw_exhaustion = False
        started = time.monotonic()
        timeout = self.settings.role_timeout_s
        self.ledger.event(
            "role.started", stage=req.stage, role=req.role, model=spec.model, cwd=str(req.cwd)
        )

        async def drain() -> None:
            nonlocal saw_exhaustion
            async for message in query(prompt=req.task, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            result.tool_calls += 1
                elif isinstance(message, RateLimitEvent):
                    self._record_rate_limit(result, message.rate_limit_info, req.stage)
                    if result.utilization.get(result.rate_limit_window or "", 0.0) >= 0.98:
                        saw_exhaustion = True
                elif isinstance(message, ResultMessage):
                    result.cost_usd = float(message.total_cost_usd or 0.0)
                    result.session_id = message.session_id
                    result.terminal_reason = message.terminal_reason or message.subtype
                    result.is_error = bool(message.is_error)
                    result.structured = message.structured_output
                    if message.api_error_status == 429:
                        result.rate_limited = True
                    if message.result:
                        chunks.append(message.result)

        try:
            await asyncio.wait_for(drain(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            elapsed = time.monotonic() - started
            # A stall right after the window filled up is a usage problem, not a
            # role problem: retrying it would only wait out the same window
            # again. Diagnose it as what it is so the run pauses and resumes.
            if saw_exhaustion:
                result.rate_limited = True
                result.terminal_reason = (
                    f"stalled for {elapsed / 60:.0f} min with the usage window exhausted"
                )
            else:
                result.is_error = True
                result.terminal_reason = f"timed out after {elapsed / 60:.0f} min"
            self.ledger.event(
                "role.timeout",
                stage=req.stage,
                role=req.role,
                seconds=round(elapsed),
                exhausted=saw_exhaustion,
            )
        except Exception as exc:  # a mid-run SDK failure is a role failure, not a crash
            result.is_error = True
            result.terminal_reason = f"exception: {type(exc).__name__}: {exc}"
            self.ledger.event(
                "role.failed", stage=req.stage, role=req.role, error=str(exc)
            )

        result.text = "\n".join(c for c in chunks if c).strip()
        result.denials = denials
        if result.rate_limited:
            self.ledger.event(
                "usage.limit_reached",
                stage=req.stage,
                role=req.role,
                window=result.rate_limit_window,
                resets_at=result.resets_at,
            )
        self.ledger.event(
            "role.finished",
            stage=req.stage,
            role=req.role,
            cost_usd=result.cost_usd,
            tool_calls=result.tool_calls,
            terminal_reason=result.terminal_reason,
            is_error=result.is_error,
            denials=denials,
        )
        return result


def _record_rate_limit_impl(result: RoleResult, info: Any, ledger: Ledger, stage: str) -> None:
    """Read the CLI's rate-limit report onto the result.

    The top-level `utilization` came back `None` in practice; the per-window
    numbers live under `raw["unifiedWindows"]`, so read both and prefer whatever
    is actually populated.
    """
    status = getattr(info, "status", None)
    result.rate_limit_window = getattr(info, "rate_limit_type", None)
    result.resets_at = getattr(info, "resets_at", None)

    raw = getattr(info, "raw", None) or {}
    windows = raw.get("unifiedWindows") or {}
    utilization: dict[str, float] = {}
    for name, window in windows.items():
        value = window.get("utilization")
        if isinstance(value, (int, float)):
            utilization[name] = float(value)
    top = getattr(info, "utilization", None)
    if not utilization and isinstance(top, (int, float)) and result.rate_limit_window:
        utilization[result.rate_limit_window] = float(top)
    result.utilization = utilization
    if utilization or status != "allowed":
        ledger.record_usage(status or "allowed", result.rate_limit_window, result.resets_at, utilization)

    if status == "rejected":
        result.rate_limited = True
    elif status == "allowed_warning":
        ledger.event(
            "usage.warning",
            stage=stage,
            window=result.rate_limit_window,
            utilization=utilization,
            resets_at=result.resets_at,
        )


#: A scripted response: either literal text, or a callable that may also write
#: artifacts to disk exactly as a real role would.
Script = str | Callable[[RoleRequest], "str | Awaitable[str]"]


class ScriptedRunner:
    """Replays canned role outputs so the pipeline can be tested for free.

    Lookup order for a request is `"<stage>:<role>"`, then `"<role>"`. A missing
    entry is a test failure, not a silent pass.
    """

    def __init__(self, scripts: dict[str, Script], cost_per_call: float = 0.0) -> None:
        self.scripts = scripts
        self.cost_per_call = cost_per_call
        self.calls: list[RoleRequest] = []

    def _lookup(self, req: RoleRequest) -> Script:
        for key in (f"{req.stage}:{req.role}", req.role):
            if key in self.scripts:
                return self.scripts[key]
        raise KeyError(
            f"ScriptedRunner has no script for stage={req.stage!r} role={req.role!r}; "
            f"known keys: {sorted(self.scripts)}"
        )

    async def invoke(self, req: RoleRequest) -> RoleResult:
        self.calls.append(req)
        script = self._lookup(req)
        if callable(script):
            out = script(req)
            if asyncio.iscoroutine(out):
                out = await out
            text = str(out)
        else:
            text = script
        return RoleResult(
            role=req.role,
            text=text,
            cost_usd=self.cost_per_call,
            terminal_reason="success",
            session_id=f"scripted-{len(self.calls)}",
        )


class MeteredRunner:
    """Wraps any Runner so every invocation is billed to the ledger.

    Metering belongs here rather than inside `SDKRunner`: the budget must hold
    whichever runner the orchestrator was handed, and a runner that forgets to
    record its spend would otherwise disable the project ceiling silently.
    """

    def __init__(self, inner: Runner, ledger: Ledger) -> None:
        self.inner = inner
        self.ledger = ledger

    async def invoke(self, req: RoleRequest) -> RoleResult:
        result = await self.inner.invoke(req)
        self.ledger.add_cost(
            req.stage, req.role, result.cost_usd, terminal_reason=result.terminal_reason
        )
        if result.utilization or result.rate_limited:
            self.ledger.record_usage(
                "rejected" if result.rate_limited else "allowed",
                result.rate_limit_window,
                result.resets_at,
                result.utilization,
            )

        # A failed invocation used to vanish here: the role produced nothing,
        # the artifact contract failed, and the stage burned every repair
        # attempt on a problem no role could fix. Raising makes the cause
        # visible at the point it happened.
        if result.rate_limited:
            raise UsageLimitReached(result.rate_limit_window, result.resets_at)
        if result.is_error:
            raise RoleError(req.role, result.terminal_reason)
        return result


def build_runner(ledger: Ledger, settings: Settings | None = None) -> Runner:
    return MeteredRunner(SDKRunner(ledger, settings), ledger)
