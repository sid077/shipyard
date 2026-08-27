"""Human approval gates.

Three points in the run stop and wait for you. Everything else is unattended.
A gate is just a record in `state.json` plus a briefing file in `inbox/`; the
CLI flips the record and the orchestrator resumes.

Rejection notes are not a restart - they are injected verbatim into the re-run
of the stage that produced the rejected work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from .ledger import GateStatus, Ledger


class Gate(StrEnum):
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"


GATE_INFO: dict[Gate, tuple[str, str]] = {
    Gate.G0: (
        "Opportunity",
        "Is this worth building? Market, competitors, wedge, monetization model.",
    ),
    Gate.G1: (
        "Specification",
        "Is this the right product? PRD, monetization spec, screen inventory.",
    ),
    Gate.G2: (
        "Release",
        "Ship it? Builds, store listing, privacy artifacts, runbook.",
    ),
}

#: Which stage each gate re-runs when rejected.
GATE_OWNER_STAGE: dict[Gate, str] = {
    Gate.G0: "s10_research",
    Gate.G1: "s20_definition",
    Gate.G2: "s80_release",
}


def request(ledger: Ledger, gate: Gate, briefing: str) -> GateStatus:
    """Raise a gate. Returns its status after the request."""
    record = ledger.state.gate(gate.value)
    if record.status in (GateStatus.APPROVED, GateStatus.REJECTED):
        return record.status
    title, question = GATE_INFO[gate]
    body = (
        f"# Gate {gate.value} - {title}\n\n"
        f"**{question}**\n\n"
        f"Project: `{ledger.state.slug}` - {ledger.state.title}\n"
        f"Spend so far: ${ledger.state.cost_usd:.2f}\n\n"
        f"---\n\n{briefing.strip()}\n\n"
        f"---\n\n"
        f"## Decide\n\n"
        f"```\n"
        f"shipyard gate approve {ledger.state.slug} {gate.value}\n"
        f"shipyard gate reject  {ledger.state.slug} {gate.value} --notes \"what to change\"\n"
        f"```\n"
    )
    ledger.write_inbox(f"{gate.value}.md", body)
    record.status = GateStatus.PENDING
    ledger.save()
    ledger.event("gate.requested", gate=gate.value)
    return record.status


def decide(
    ledger: Ledger,
    gate: Gate,
    approved: bool,
    notes: str = "",
    decided_by: str = "human",
) -> None:
    record = ledger.state.gate(gate.value)
    record.status = GateStatus.APPROVED if approved else GateStatus.REJECTED
    record.notes = notes
    record.decided_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Recorded so the trail never claims a person read something they did not.
    record.decided_by = decided_by
    ledger.save()
    ledger.event(
        "gate.decided",
        gate=gate.value,
        status=str(record.status),
        notes=notes,
        decided_by=decided_by,
    )


def status(ledger: Ledger, gate: Gate) -> GateStatus:
    return ledger.state.gate(gate.value).status


def feedback(ledger: Ledger, gate: Gate) -> str:
    """Rejection notes, shaped for injection into the owning stage's prompt."""
    record = ledger.state.gate(gate.value)
    if record.status != GateStatus.REJECTED or not record.notes:
        return ""
    return (
        f"The human operator rejected gate {gate.value} with these instructions. "
        f"They override your previous conclusions:\n\n{record.notes.strip()}"
    )


def clear_rejection(ledger: Ledger, gate: Gate) -> None:
    """Called once the owning stage has re-run with the operator's notes."""
    record = ledger.state.gate(gate.value)
    if record.status == GateStatus.REJECTED:
        record.status = GateStatus.NOT_REACHED
        ledger.save()
        ledger.event("gate.rearmed", gate=gate.value)
