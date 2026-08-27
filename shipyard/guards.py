"""Hard limits on what any role may do, enforced as a PreToolUse hook.

Two rules the org can never talk its way around:

1. **It cannot ship.** Publishing, submitting, releasing and pushing are the
   human's actions. An agent that tries is denied, and the attempt is logged.
2. **It cannot escape its workspace.** Writes must land inside the paths the
   pipeline handed the role.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

#: (pattern, why) - matched case-insensitively against the whole Bash command.
FORBIDDEN_BASH: list[tuple[str, str]] = [
    (r"\bgit\s+push\b", "shipping is the human's action: the org never pushes"),
    (r"\bgit\s+remote\s+(add|set-url)\b", "remotes are configured by the operator"),
    (r"\beas\s+submit\b", "store submission is the human's action"),
    (r"\bexpo\s+publish\b", "publishing is the human's action"),
    (r"\bnpm\s+publish\b", "publishing is the human's action"),
    (r"\b(vercel|netlify|fly|wrangler)\b.*\b(deploy|--prod)\b", "deploys are the human's action"),
    (r"\bgh\s+(pr|release|repo|api)\b", "the org does not touch GitHub directly"),
    (r"\brm\s+-[a-z]*[rf][a-z]*\s+(/|~|\$HOME|\*)(\s|$)", "refusing a destructive recursive delete"),
    (r"\bcurl\b[^|;&]*\|\s*(ba|z|fi)?sh\b", "refusing to pipe a download into a shell"),
    (r"\bwget\b[^|;&]*\|\s*(ba|z|fi)?sh\b", "refusing to pipe a download into a shell"),
    (r"\b(shutdown|reboot|halt|mkfs|dd\s+if=)\b", "refusing a host-level operation"),
    (r":\s*\(\s*\)\s*\{.*\}\s*;\s*:", "refusing a fork bomb"),
    (r"\bgit\s+(commit|merge|rebase|worktree|checkout|branch)\b",
     "git is owned by the orchestrator, not by roles: edit files and let the pipeline commit"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE | re.DOTALL), why) for p, why in FORBIDDEN_BASH]

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}


def check_bash(command: str) -> str | None:
    """Return the reason this command is forbidden, or None if it is allowed."""
    for pattern, why in _COMPILED:
        if pattern.search(command):
            return why
    return None


def check_write_path(path_str: str, allowed_roots: Sequence[Path]) -> str | None:
    """Return a reason the write is forbidden, or None if it is allowed."""
    if not path_str:
        return None
    try:
        target = Path(path_str).resolve()
    except (OSError, ValueError):
        return f"cannot resolve write path {path_str!r}"
    for root in allowed_roots:
        try:
            target.relative_to(Path(root).resolve())
        except ValueError:
            continue
        return None
    roots = ", ".join(str(r) for r in allowed_roots)
    return f"write to {target} is outside this role's workspace ({roots})"


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Blocked by Shipyard guard: {reason}",
        }
    }


def make_guard(
    allowed_roots: Sequence[Path],
    on_deny: Callable[[str, str], None] | None = None,
):
    """Build the PreToolUse hook for a role confined to `allowed_roots`."""

    roots = [Path(r) for r in allowed_roots]

    async def guard(input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        data = input_data if isinstance(input_data, dict) else getattr(input_data, "__dict__", {})
        tool_name = data.get("tool_name") or getattr(input_data, "tool_name", "")
        tool_input = data.get("tool_input") or getattr(input_data, "tool_input", {}) or {}

        reason: str | None = None
        if tool_name == "Bash":
            reason = check_bash(str(tool_input.get("command", "")))
        elif tool_name in WRITE_TOOLS:
            target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            reason = check_write_path(str(target), roots)

        if reason:
            if on_deny:
                on_deny(str(tool_name), reason)
            return _deny(reason)
        return {}

    return guard
