"""The single place the Claude Agent SDK is called.

Every role invocation in the org funnels through `Runner.invoke`. That is what
makes spend bounded, tool access least-privilege, and the whole pipeline
testable: swap `SDKRunner` for `ScriptedRunner` and the orchestrator runs end to
end with no API calls.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .config import Settings, load_settings
from .guards import make_guard
from .ledger import Ledger
from .roles import RoleSpec, get_role


@dataclass
class RoleRequest:
    role: str
    task: str
    cwd: Path
    stage: str
    #: Directories this role may write to. Defaults to `[cwd]`.
    allowed_roots: list[Path] = field(default_factory=list)
    resume: str | None = None
    budget_usd: float | None = None
    extra_tools: list[str] = field(default_factory=list)

    def roots(self) -> list[Path]:
        return self.allowed_roots or [self.cwd]


@dataclass
class RoleResult:
    role: str
    text: str
    cost_usd: float = 0.0
    session_id: str | None = None
    terminal_reason: str = "unknown"
    is_error: bool = False
    tool_calls: int = 0
    denials: list[str] = field(default_factory=list)
    structured: Any = None

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
        guard = make_guard(roots, on_deny=lambda tool, why: denials.append(f"{tool}: {why}"))
        tools = list(dict.fromkeys([*spec.tools, *req.extra_tools]))
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt(spec),
            model=spec.model,
            effort=spec.effort,
            thinking={"type": "adaptive"},
            allowed_tools=tools,
            disallowed_tools=spec.disallowed,
            permission_mode="acceptEdits",
            cwd=str(req.cwd),
            add_dirs=[str(r) for r in roots if Path(r) != Path(req.cwd)],
            max_turns=spec.max_turns,
            max_budget_usd=req.budget_usd or spec.budget_usd,
            # Hermetic: no user/project settings, CLAUDE.md or plugins leak in.
            setting_sources=[],
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
        self.ledger.event(
            "role.started", stage=req.stage, role=req.role, model=spec.model, cwd=str(req.cwd)
        )

        try:
            async for message in query(prompt=req.task, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            result.tool_calls += 1
                elif isinstance(message, ResultMessage):
                    result.cost_usd = float(message.total_cost_usd or 0.0)
                    result.session_id = message.session_id
                    result.terminal_reason = message.terminal_reason or message.subtype
                    result.is_error = bool(message.is_error)
                    result.structured = message.structured_output
                    if message.result:
                        chunks.append(message.result)
        except Exception as exc:  # a mid-run SDK failure is a role failure, not a crash
            result.is_error = True
            result.terminal_reason = f"exception: {type(exc).__name__}: {exc}"
            self.ledger.event(
                "role.failed", stage=req.stage, role=req.role, error=str(exc)
            )

        result.text = "\n".join(c for c in chunks if c).strip()
        result.denials = denials
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
        return result


def build_runner(ledger: Ledger, settings: Settings | None = None) -> Runner:
    return MeteredRunner(SDKRunner(ledger, settings), ledger)
