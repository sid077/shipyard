"""Composing the per-invocation task prompt.

A role's system prompt says who it is; the task prompt says what to read, what
to write, and what went wrong last time. Keeping the two separate means the
system prompt stays byte-identical across attempts.
"""

from __future__ import annotations

from pathlib import Path

from .contracts import Artifact

_RULES = """\
## Working rules

- Read every input listed above before you write anything.
- Write each output file to the exact path given, as a single JSON document
  that validates against the schema shown. No comments, no trailing commas, no
  prose outside the JSON.
- Do not invent facts. If you cannot substantiate a claim, say so in the field
  rather than filling it with a plausible number.
- Do not run git. The orchestrator owns the repository.
- Do not create files that were not asked for.
- When you are finished, reply with a two-sentence summary of what you wrote.
"""


def _schema_block(cls: type[Artifact], project_dir: Path) -> str:
    return (
        f"### Write `{cls.rel_path}`\n"
        f"Absolute path: `{cls.full_path(project_dir)}`\n\n"
        f"It must validate against this JSON Schema:\n\n"
        f"```json\n{cls.schema_hint()}\n```\n"
    )


def compose(
    *,
    objective: str,
    project_dir: Path,
    inputs: list[Path] | None = None,
    outputs: list[type[Artifact]] | None = None,
    guidance: str = "",
    feedback: str = "",
) -> str:
    parts: list[str] = [f"## Objective\n\n{objective.strip()}\n"]

    inputs = inputs or []
    if inputs:
        listing = "\n".join(f"- `{p}`" for p in inputs)
        parts.append(f"## Read first\n\n{listing}\n")

    for cls in outputs or []:
        parts.append("## Output\n\n" + _schema_block(cls, project_dir))

    if guidance.strip():
        parts.append(f"## Guidance\n\n{guidance.strip()}\n")

    parts.append(_RULES)

    # Feedback goes last so it is the most recent thing in context.
    if feedback.strip():
        parts.append(
            "## You are being re-run\n\n"
            "The previous attempt was rejected. Address this in full; everything "
            "else about the objective is unchanged.\n\n"
            f"{feedback.strip()}\n"
        )

    return "\n".join(parts)


def existing(*paths: Path) -> list[Path]:
    """Filter to the inputs that actually exist, so prompts never point at nothing."""
    return [p for p in paths if p.exists()]
