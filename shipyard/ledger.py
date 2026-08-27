"""Durable run state.

Two files per project, both under `.shipyard/`:

* `state.json`  - the resumable snapshot, rewritten atomically after every step.
* `events.jsonl` - an append-only trace of everything that happened.

If the process dies, `state.json` is the truth and `shipyard resume` picks up at
the first stage that is not `done`.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

STATE_DIRNAME = ".shipyard"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    BLOCKED = "blocked"


class GateStatus(StrEnum):
    NOT_REACHED = "not_reached"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TicketStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    MERGED = "merged"
    BLOCKED = "blocked"


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    note: str = ""


class GateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GateStatus = GateStatus.NOT_REACHED
    notes: str = ""
    decided_at: str | None = None
    #: "human" or "machine". A gate approved by a flag must never look like one
    #: a person actually read.
    decided_by: str | None = None


class UsageWindow(BaseModel):
    """The account's rate-limit position, as last reported by the CLI.

    This is the ceiling that actually stops a run - a dollar estimate is not.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = "allowed"
    window: str | None = None
    resets_at: int | None = None
    #: window name -> fraction consumed, 0.0-1.0
    utilization: dict[str, float] = {}
    observed_at: str | None = None


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    current_stage: str | None = None
    stages: dict[str, StageRecord] = {}
    gates: dict[str, GateRecord] = {}
    tickets: dict[str, TicketStatus] = {}
    cost_usd: float = 0.0
    usage: UsageWindow = UsageWindow()
    blocked_reason: str | None = None

    def stage(self, key: str) -> StageRecord:
        return self.stages.setdefault(key, StageRecord())

    def gate(self, key: str) -> GateRecord:
        return self.gates.setdefault(key, GateRecord())


class Ledger:
    """Owns `state.json` and `events.jsonl` for one project."""

    def __init__(self, project_dir: Path, state: ProjectState) -> None:
        self.project_dir = Path(project_dir)
        self.state = state

    # -- construction ------------------------------------------------------

    @property
    def dir(self) -> Path:
        return self.project_dir / STATE_DIRNAME

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    @property
    def events_path(self) -> Path:
        return self.dir / "events.jsonl"

    @property
    def cost_path(self) -> Path:
        return self.dir / "cost.jsonl"

    @property
    def inbox(self) -> Path:
        return self.project_dir / "inbox"

    @classmethod
    def create(cls, project_dir: Path, slug: str, title: str) -> Self:
        project_dir = Path(project_dir)
        (project_dir / STATE_DIRNAME).mkdir(parents=True, exist_ok=True)
        (project_dir / "inbox").mkdir(parents=True, exist_ok=True)
        ledger = cls(project_dir, ProjectState(slug=slug, title=title))
        ledger.save()
        ledger.event("project.created", slug=slug, title=title)
        return ledger

    @classmethod
    def open(cls, project_dir: Path) -> Self:
        project_dir = Path(project_dir)
        path = project_dir / STATE_DIRNAME / "state.json"
        if not path.is_file():
            raise FileNotFoundError(f"no shipyard project at {project_dir}")
        state = ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(project_dir, state)

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        """Atomic rewrite - a crash mid-write must not corrupt the snapshot."""
        self.state.updated_at = _now()
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.state.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.state_path)

    def event(self, kind: str, **fields: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": _now(), "mono": round(time.monotonic(), 3), "kind": kind, **fields}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    # -- cost --------------------------------------------------------------

    def add_cost(self, stage: str, role: str, usd: float, **extra: Any) -> None:
        self.state.cost_usd = round(self.state.cost_usd + max(usd, 0.0), 6)
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.cost_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {"ts": _now(), "stage": stage, "role": role, "usd": usd, **extra}
                )
                + "\n"
            )
        self.save()

    def cost_rows(self) -> list[dict[str, Any]]:
        if not self.cost_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.cost_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def stage_cost(self, stage: str) -> float:
        return round(sum(r["usd"] for r in self.cost_rows() if r["stage"] == stage), 6)

    # -- stage transitions -------------------------------------------------

    def stage_started(self, key: str) -> None:
        rec = self.state.stage(key)
        rec.status = StageStatus.RUNNING
        rec.attempts += 1
        rec.started_at = rec.started_at or _now()
        rec.note = ""
        self.state.current_stage = key
        self.state.blocked_reason = None
        self.save()
        self.event("stage.started", stage=key, attempt=rec.attempts)

    def stage_done(self, key: str, note: str = "") -> None:
        rec = self.state.stage(key)
        rec.status = StageStatus.DONE
        rec.finished_at = _now()
        rec.note = note
        self.save()
        self.event("stage.done", stage=key, note=note)

    def stage_blocked(self, key: str, reason: str) -> None:
        rec = self.state.stage(key)
        rec.status = StageStatus.BLOCKED
        rec.note = reason
        self.state.blocked_reason = f"{key}: {reason}"
        self.save()
        self.event("stage.blocked", stage=key, reason=reason)

    def record_usage(
        self,
        status: str,
        window: str | None,
        resets_at: int | None,
        utilization: dict[str, float],
    ) -> None:
        self.state.usage = UsageWindow(
            status=status,
            window=window,
            resets_at=resets_at,
            utilization=utilization or self.state.usage.utilization,
            observed_at=_now(),
        )
        self.save()

    def write_inbox(self, name: str, body: str) -> Path:
        self.inbox.mkdir(parents=True, exist_ok=True)
        path = self.inbox / name
        path.write_text(body, encoding="utf-8")
        self.event("inbox.written", file=str(path.relative_to(self.project_dir)))
        return path
