"""The stage graph.

`STAGES` is the whole pipeline, in order. Adding a stage means adding it here;
the orchestrator has no other source of truth.
"""

from __future__ import annotations

from . import Stage
from .build import BUILD_STAGES
from .discovery import DISCOVERY_STAGES

STAGES: list[Stage] = [*DISCOVERY_STAGES, *BUILD_STAGES]

STAGE_KEYS: list[str] = [s.key for s in STAGES]


def get_stage(key: str) -> Stage:
    for stage in STAGES:
        if stage.key == key:
            return stage
    raise KeyError(f"unknown stage {key!r}; known stages: {STAGE_KEYS}")


def validate_graph(stages: list[Stage] | None = None) -> list[str]:
    """Static checks on the pipeline. Returns a list of problems (empty is good)."""
    stages = stages or STAGES
    problems: list[str] = []
    seen_keys: set[str] = set()
    produced: set[str] = set()

    for index, stage in enumerate(stages):
        if stage.key in seen_keys:
            problems.append(f"duplicate stage key {stage.key!r}")
        seen_keys.add(stage.key)
        if not stage.key or not stage.title:
            problems.append(f"stage at index {index} is missing key or title")
        for cls in stage.requires:
            if cls.rel_path not in produced:
                problems.append(
                    f"{stage.key} requires {cls.rel_path}, which no earlier stage produces"
                )
        for cls in stage.outputs:
            if cls.rel_path in produced:
                problems.append(
                    f"{stage.key} re-produces {cls.rel_path}, already written upstream"
                )
            produced.add(cls.rel_path)
        if stage.audit and not stage.dod.strip():
            problems.append(f"{stage.key} is audited but declares no Definition of Done")

    from ..gates import GATE_OWNER_STAGE

    gated = {s.gate_after: s.key for s in stages if s.gate_after}
    for gate, owner in GATE_OWNER_STAGE.items():
        if gate not in gated:
            continue
        if owner not in seen_keys:
            problems.append(f"gate {gate} names owner stage {owner!r}, which does not exist")
            continue
        owner_index = next(i for i, s in enumerate(stages) if s.key == owner)
        gate_index = next(i for i, s in enumerate(stages) if s.key == gated[gate])
        if owner_index > gate_index:
            problems.append(
                f"gate {gate} owner {owner!r} runs after the gate itself - "
                f"a rejection could not re-run it"
            )
    return problems
