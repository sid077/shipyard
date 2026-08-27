"""Definition-of-Done audit.

The deterministic checks - contract validation and executed commands - are the
real gate and they fail closed. The critic is a second net that catches what a
schema cannot: a PRD with no testable acceptance criteria, competitor research
with invented pricing, a backlog whose tickets are not vertical slices.

Because it is a net and not the gate, an auditor that returns unparseable output
twice is skipped rather than allowed to deadlock a stage that already passed
every machine check.
"""

from __future__ import annotations

from pathlib import Path

from .contracts import Verdict, coerce_verdict
from .ledger import Ledger
from .runner import RoleRequest, Runner
from .verify import CheckReport

_TASK = """Audit the output of pipeline stage `{stage}` against its Definition of Done.

## Definition of Done
{dod}

## Artifacts to audit
{artifacts}

## Machine checks already run
{checks}

Read every artifact listed above before judging. Judge only what the Definition
of Done asks for - do not invent additional requirements, and do not restate
issues the machine checks already caught.

Reply with a single JSON object and nothing else:

{{
  "verdict": "pass" | "fail",
  "summary": "one sentence",
  "findings": [
    {{"severity": "blocking" | "advisory",
      "where": "file path or artifact field",
      "problem": "what is wrong",
      "fix": "the specific change that would resolve it"}}
  ]
}}

Return "fail" only when at least one finding is "blocking". A blocking finding
must be something that will actively damage a later stage, not a matter of taste.
"""


async def audit(
    runner: Runner,
    ledger: Ledger,
    *,
    stage: str,
    project_dir: Path,
    dod: str,
    artifacts: list[Path],
    checks: CheckReport | None = None,
) -> Verdict:
    listing = "\n".join(f"- {p}" for p in artifacts) or "- (none)"
    task = _TASK.format(
        stage=stage,
        dod=dod.strip(),
        artifacts=listing,
        checks=checks.summary() if checks else "none",
    )

    for attempt in (1, 2):
        result = await runner.invoke(
            RoleRequest(
                role="critic",
                task=task,
                cwd=project_dir,
                stage=stage,
                allowed_roots=[project_dir],
            )
        )
        verdict = coerce_verdict(result.structured, result.text)
        if verdict is not None:
            ledger.event(
                "critic.verdict",
                stage=stage,
                verdict=verdict.verdict,
                blocking=len(verdict.blocking),
                summary=verdict.summary,
            )
            return verdict
        ledger.event("critic.unparseable", stage=stage, attempt=attempt)

    ledger.event("critic.skipped", stage=stage, reason="unparseable after 2 attempts")
    return Verdict(
        verdict="pass",
        summary="critic output was unparseable twice; machine checks stand alone",
    )
