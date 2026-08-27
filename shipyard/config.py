"""Central configuration: model tiers, budgets, and filesystem layout.

Everything tunable about how much the org spends and which model does which job
lives here, so retuning cost never means touching pipeline logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Model tiers. Roles refer to tiers, not model IDs, so a single edit here
# retargets the whole org.
MODELS: dict[str, str] = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
}

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent


def _env_float(name: str) -> float | None:
    """A spend ceiling, or None for unlimited.

    Ceilings are opt-in: the account's usage window is the real limit, and a
    dollar estimate that halts a run early is worse than no estimate at all.
    """
    raw = os.environ.get(name)
    return float(raw) if raw else None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """Runtime knobs, all overridable via SHIPYARD_* environment variables."""

    repo_root: Path = REPO_ROOT
    projects_dir: Path = field(default_factory=lambda: REPO_ROOT / "projects")
    templates_dir: Path = field(default_factory=lambda: REPO_ROOT / "templates")
    prompts_dir: Path = field(default_factory=lambda: REPO_ROOT / "prompts")
    scouting_dir: Path = field(default_factory=lambda: REPO_ROOT / "scouting")

    # How many times a role may be re-invoked with critic feedback before the
    # stage escalates to a human.
    max_repairs: int = field(default_factory=lambda: _env_int("SHIPYARD_MAX_REPAIRS", 3))
    # Parallel `dev` workers during the build loop.
    build_concurrency: int = field(
        default_factory=lambda: _env_int("SHIPYARD_BUILD_CONCURRENCY", 3)
    )
    # Optional spend ceilings. Unset by default: the run stops when the
    # account's usage window is exhausted, which is the truth rather than an
    # estimate. Set SHIPYARD_PROJECT_BUDGET_USD to reinstate a hard cap.
    project_budget_usd: float | None = field(
        default_factory=lambda: _env_float("SHIPYARD_PROJECT_BUDGET_USD")
    )
    stage_budget_usd: float | None = field(
        default_factory=lambda: _env_float("SHIPYARD_STAGE_BUDGET_USD")
    )
    # Wall-clock ceiling for a single verification command.
    check_timeout_s: int = field(
        default_factory=lambda: _env_int("SHIPYARD_CHECK_TIMEOUT_S", 900)
    )
    # Wall-clock ceiling for one role invocation. Without this a role that
    # stalls - most often the CLI silently retrying behind an exhausted usage
    # window - hangs the whole org with no signal to the operator.
    role_timeout_s: int = field(
        default_factory=lambda: _env_int("SHIPYARD_ROLE_TIMEOUT_S", 1800)
    )

    def project_dir(self, slug: str) -> Path:
        return self.projects_dir / slug


def load_settings() -> Settings:
    root = os.environ.get("SHIPYARD_ROOT")
    if not root:
        return Settings()
    base = Path(root).resolve()
    return Settings(
        repo_root=base,
        projects_dir=base / "projects",
        templates_dir=base / "templates",
        prompts_dir=base / "prompts",
    )
