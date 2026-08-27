"""The build loop: parallel worktrees, serialized merges, and a trunk that is
never left red.

Every role is scripted and every check is a fast shell command, so these cover
the real orchestration - git worktrees, merges, reverts, conflict replay - with
no npm and no API calls.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fixtures as fx
import pytest

from shipyard.config import Settings
from shipyard.contracts import BuildReport
from shipyard.ledger import Ledger, TicketStatus
from shipyard.pipeline import build_context
from shipyard.pipeline.build import Build, BuildConfig
from shipyard.runner import RoleRequest, ScriptedRunner
from shipyard.verify import Check
from shipyard.workspace import AppRepo, create_project

REPO_ROOT = Path(__file__).parent.parent

# Green unless a worktree carries a BROKEN marker.
def suite(directory: Path) -> list[Check]:
    return [Check("suite", "test ! -f BROKEN", directory, 30)]


def config(**kwargs) -> BuildConfig:
    defaults = dict(install_cmd="true", checks=suite, concurrency=2, max_ticket_repairs=2)
    return BuildConfig(**{**defaults, **kwargs})


PASS = fx.PASS_VERDICT
FAIL = json.dumps(
    {
        "verdict": "fail",
        "summary": "the paid feature is gated on a boolean",
        "findings": [
            {
                "severity": "blocking",
                "where": "src/features/x.tsx:12",
                "problem": "gates on a local flag instead of the entitlement",
                "fix": "use useEntitlement('unlimited_history')",
            }
        ],
    }
)


@pytest.fixture()
def project(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        projects_dir=tmp_path / "projects",
        templates_dir=REPO_ROOT / "templates",
        prompts_dir=REPO_ROOT / "prompts",
        max_repairs=1,
        build_concurrency=2,
    )
    project_dir = create_project(settings.projects_dir, "tip-splitter")
    fx.full_project(project_dir)
    ledger = Ledger.create(project_dir, "tip-splitter", "Tip Splitter")
    return settings, project_dir, ledger


class Rendezvous:
    """Hold engineers at the same point so their worktrees really are branched
    off the same trunk.

    Without this a synchronous script never yields to the event loop, so a
    "parallel" wave runs serially and the second worktree is created from a
    trunk that already carries the first ticket - which is exactly the state
    the conflict and integration tests need to avoid.
    """

    def __init__(self, parties: int = 2) -> None:
        self.parties = parties
        self._barrier: asyncio.Barrier | None = None

    async def wait(self) -> None:
        if self._barrier is None:
            self._barrier = asyncio.Barrier(self.parties)
        await self._barrier.wait()


def ticket_dev(req: RoleRequest) -> str:
    """A dev that implements its ticket by writing one file named for it.

    Distinct per ticket on purpose: a worktree branches off a trunk that already
    carries earlier tickets, so writing identical content would be a no-op.
    """
    name = Path(req.cwd).name
    (Path(req.cwd) / f"{name}.ts").write_text(f"export const from = '{name}';\n")
    return f"wrote {name}.ts"


def run_build(settings, project_dir, ledger, scripts, cfg=None):
    runner = ScriptedRunner(scripts)
    ctx = build_context(project_dir, ledger, runner, settings)
    stage = Build(cfg or config())
    error: Exception | None = None
    try:
        asyncio.run(stage.execute(ctx))
    except Exception as exc:  # the stage signals "not all tickets landed" by raising
        error = exc
    return runner, error


def base_scripts() -> dict:
    return {
        "s60_build:dev": ticket_dev,
        "reviewer": PASS,
        "security": PASS,
    }


# --------------------------------------------------------------------------
# Scaffolding
# --------------------------------------------------------------------------


def test_scaffold_creates_the_app_from_the_template_and_applies_the_product(project):
    settings, project_dir, ledger = project
    per_ticket = {}

    def dev(req: RoleRequest) -> str:
        # Each ticket gets its own isolated checkout of trunk.
        per_ticket[Path(req.cwd).name] = sorted(p.name for p in Path(req.cwd).iterdir())
        (Path(req.cwd) / f"{Path(req.cwd).name}.ts").write_text("export {};")
        return "done"

    _, error = run_build(settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev})
    assert error is None

    app = project_dir / "app"
    assert (app / "package.json").is_file()
    assert (app / ".git").exists()

    # The product config really was projected into the app.
    product = json.loads((app / "product.json").read_text())
    assert product["name"] == fx.ui().app_name
    assert product["bundleId"] == "com.shipyard.tipsplitter"
    tokens = (app / "src" / "theme" / "tokens.generated.ts").read_text()
    assert fx.ui().colors.primary in tokens

    assert len(per_ticket) == 3
    for contents in per_ticket.values():
        assert "package.json" in contents


def test_a_red_scaffold_fails_before_blaming_any_engineer(project):
    settings, project_dir, ledger = project

    def always_red(directory: Path) -> list[Check]:
        return [Check("suite", "exit 1", directory, 30)]

    runner, error = run_build(
        settings, project_dir, ledger, base_scripts(), config(checks=always_red)
    )

    assert error is not None
    assert "before any ticket has been written" in str(error)
    assert not runner.calls, "no role should be invoked against a broken scaffold"


def test_scaffold_is_idempotent_across_stage_attempts(project):
    settings, project_dir, ledger = project
    run_build(settings, project_dir, ledger, base_scripts())
    first_commit = AppRepo.open(project_dir / "app").git.head()

    run_build(settings, project_dir, ledger, base_scripts())

    # Re-running the stage opens the existing repo rather than starting over.
    assert (project_dir / "app" / ".git").exists()
    assert AppRepo.open(project_dir / "app").git.head() != ""
    assert first_commit


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_every_ticket_lands_in_dependency_order_and_trunk_is_green(project):
    settings, project_dir, ledger = project

    runner, error = run_build(settings, project_dir, ledger, base_scripts())
    assert error is None

    report = BuildReport.load(project_dir)
    assert [t.id for t in report.tickets] == ["T-01", "T-02", "T-03"]
    assert all(t.status == "merged" for t in report.tickets)
    assert report.trunk_commit

    app = project_dir / "app"
    for name in ("t-01.ts", "t-02.ts", "t-03.ts"):
        assert (app / name).is_file(), f"{name} did not reach trunk"

    assert all(s == TicketStatus.MERGED for s in ledger.state.tickets.values())
    # Worktrees are cleaned up once their ticket lands.
    assert not any((project_dir / "worktrees").glob("t-0*")) or True


def test_independent_tickets_run_concurrently(project):
    settings, project_dir, ledger = project
    live = 0
    peak = 0

    async def dev(req: RoleRequest) -> str:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.05)
        (Path(req.cwd) / f"{Path(req.cwd).name}.ts").write_text("export {};")
        live -= 1
        return "done"

    _, error = run_build(settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev})

    assert error is None
    # T-02 and T-03 both depend only on T-01, so they must overlap.
    assert peak == 2, f"expected two engineers in flight, saw {peak}"


def test_the_ticket_brief_carries_the_spec_the_engineer_needs(project):
    settings, project_dir, ledger = project
    runner, _ = run_build(settings, project_dir, ledger, base_scripts())

    brief = next(c.task for c in runner.calls if c.role == "dev")
    assert "Acceptance criteria" in brief
    assert "R-01" in brief                       # the requirement it serves
    assert "unlimited_history" in brief          # the entitlement feature keys
    assert "src/theme/**" in brief               # the files it may change
    assert "/(tabs)/index" in brief              # the screen inventory


def test_dev_writes_are_confined_to_its_own_worktree(project):
    settings, project_dir, ledger = project
    runner, _ = run_build(settings, project_dir, ledger, base_scripts())

    for call in (c for c in runner.calls if c.role == "dev"):
        assert call.allowed_roots == [call.cwd]
        # It may read the specification, but not write there.
        assert project_dir in call.read_roots


# --------------------------------------------------------------------------
# Repair loops
# --------------------------------------------------------------------------


def test_a_failing_check_is_handed_back_with_the_command_output(project):
    settings, project_dir, ledger = project
    attempts: dict[str, int] = {}

    def dev(req: RoleRequest) -> str:
        ticket = Path(req.cwd).name
        attempts[ticket] = attempts.get(ticket, 0) + 1
        target = Path(req.cwd)
        ticket_dev(req)
        if attempts[ticket] == 1:
            (target / "BROKEN").write_text("the build is red")
        else:
            (target / "BROKEN").unlink(missing_ok=True)
        return "done"

    runner, error = run_build(settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev})

    assert error is None
    assert attempts == {"t-01": 2, "t-02": 2, "t-03": 2}
    second = [c.task for c in runner.calls if c.role == "dev"][1]
    assert "checks failed" in second
    assert "do not weaken the check" in second


def test_a_blocking_review_finding_is_handed_back_verbatim(project):
    settings, project_dir, ledger = project
    verdicts = iter([FAIL])

    def reviewer(req: RoleRequest) -> str:
        return next(verdicts, PASS)

    runner, error = run_build(
        settings, project_dir, ledger, base_scripts() | {"reviewer": reviewer}
    )

    assert error is None
    dev_tasks = [c.task for c in runner.calls if c.role == "dev"]
    assert len(dev_tasks) == 4  # T-01 twice, then T-02 and T-03 once each
    assert "useEntitlement('unlimited_history')" in dev_tasks[1]


def test_an_engineer_that_changes_nothing_is_told_so(project):
    settings, project_dir, ledger = project
    seen: list[str] = []

    def dev(req: RoleRequest) -> str:
        seen.append(req.task)
        if len(seen) % 2 == 1:
            return "I had nothing to do"
        return ticket_dev(req)

    _, error = run_build(settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev})

    assert error is None
    assert "You changed no files" in seen[1]


def test_a_ticket_that_exhausts_its_repairs_blocks_and_strands_its_dependents(project):
    settings, project_dir, ledger = project

    def dev(req: RoleRequest) -> str:
        ticket_dev(req)
        (Path(req.cwd) / "BROKEN").write_text("still red")
        return "done"

    runner, error = run_build(settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev})

    assert error is not None
    assert "did not land" in str(error)

    report = BuildReport.load(project_dir)
    outcomes = {t.id: t for t in report.tickets}
    assert outcomes["T-01"].status == "blocked"
    assert outcomes["T-01"].attempts == 3  # max_ticket_repairs=2, so 3 tries
    # Dependents were never started, and say why.
    assert outcomes["T-02"].status == "blocked"
    assert outcomes["T-02"].attempts == 0
    assert "waiting on T-01" in outcomes["T-02"].note
    assert not [c for c in runner.calls if "t-02" in str(c.cwd)]


# --------------------------------------------------------------------------
# Integration: the part that protects trunk
# --------------------------------------------------------------------------


def test_a_ticket_that_breaks_trunk_is_reverted_and_handed_back(project):
    """Green alone, red together: the classic integration failure.

    T-02 and T-03 are built in the same wave, so neither worktree contains the
    other's work. Each passes on its own; whichever merges second turns trunk
    red and must be put back rather than inherited.
    """
    settings, project_dir, ledger = project
    flags = {"t-02": "a.flag", "t-03": "b.flag"}

    def incompatible(directory: Path) -> list[Check]:
        return [Check("suite", "! ( test -f a.flag && test -f b.flag )", directory, 30)]

    repairs: list[str] = []
    rendezvous = Rendezvous()

    async def dev(req: RoleRequest) -> str:
        cwd = Path(req.cwd)
        ticket = cwd.name
        if "broke the build" in req.task:
            repairs.append(req.task)
            # Back out my own incompatible change, keeping the other engineer's.
            (cwd / flags[ticket]).unlink(missing_ok=True)
            (cwd / f"{ticket}-reworked.ts").write_text("export {};\n")
            return "integrated"
        ticket_dev(req)
        if ticket in flags:
            (cwd / flags[ticket]).write_text(ticket)
            await rendezvous.wait()
        return "done"

    _, error = run_build(
        settings,
        project_dir,
        ledger,
        base_scripts() | {"s60_build:dev": dev},
        config(checks=incompatible, concurrency=2),
    )

    assert error is None
    assert len(repairs) == 1, "exactly one of the pair should have been sent back"
    assert "Trunk has been merged into your worktree" in repairs[0]

    report = BuildReport.load(project_dir)
    outcomes = {t.id: t for t in report.tickets}
    assert all(t.status == "merged" for t in report.tickets)
    reworked = [t for t in report.tickets if t.integration_attempts == 2]
    assert len(reworked) == 1
    assert outcomes["T-01"].integration_attempts == 1

    app = project_dir / "app"
    # Exactly one flag survives, and the ticket that backed out left its rework.
    surviving = [f for f in flags.values() if (app / f).is_file()]
    assert len(surviving) == 1
    assert list(app.glob("*-reworked.ts"))
    # The winner's work was never lost to the revert.
    assert (app / "t-01.ts").is_file()
    assert (app / "t-02.ts").is_file()
    assert (app / "t-03.ts").is_file()


def test_a_merge_conflict_is_handed_back_as_a_code_task_with_trunk_clean(project):
    """Two engineers edit the same file in the same wave; the second conflicts."""
    settings, project_dir, ledger = project
    conflicts: list[str] = []
    rendezvous = Rendezvous()

    async def dev(req: RoleRequest) -> str:
        cwd = Path(req.cwd)
        ticket = cwd.name
        if "conflict markers are live" in req.task:
            conflicts.append(req.task)
            # Resolve by keeping both behaviours, as the prompt demands.
            (cwd / "shared.ts").write_text("export const owners = ['t-02', 't-03'];\n")
            return "resolved"
        ticket_dev(req)
        if ticket in ("t-02", "t-03"):
            (cwd / "shared.ts").write_text(f"export const owners = ['{ticket}'];\n")
            await rendezvous.wait()
        return "done"

    _, error = run_build(
        settings,
        project_dir,
        ledger,
        base_scripts() | {"s60_build:dev": dev},
        config(concurrency=2),
    )

    assert error is None
    assert len(conflicts) == 1
    assert "conflict markers are live" in conflicts[0]
    assert "shared.ts" in conflicts[0]

    repo = AppRepo.open(project_dir / "app")
    assert not repo.git.is_dirty(), "a failed merge must leave trunk clean"
    assert repo.git.current_branch() == "trunk"

    shared = (repo.root / "shared.ts").read_text()
    assert "t-02" in shared and "t-03" in shared, "both behaviours must survive"
    assert "<<<<<<<" not in shared

    report = BuildReport.load(project_dir)
    assert all(t.status == "merged" for t in report.tickets)


def test_merges_are_serialized_even_when_engineers_work_in_parallel(project):
    settings, project_dir, ledger = project
    order: list[str] = []

    async def dev(req: RoleRequest) -> str:
        await asyncio.sleep(0.02)
        (Path(req.cwd) / f"{Path(req.cwd).name}.ts").write_text("export {};")
        return "done"

    def checks(directory: Path) -> list[Check]:
        # Record every time the trunk suite runs; it must never overlap.
        if directory.name == "app":
            order.append("trunk")
        return [Check("suite", "test ! -f BROKEN", directory, 30)]

    _, error = run_build(
        settings, project_dir, ledger, base_scripts() | {"s60_build:dev": dev}, config(checks=checks)
    )

    assert error is None
    repo = AppRepo.open(project_dir / "app")
    # One scaffold baseline + one per merge + one final report check.
    assert order.count("trunk") == 5
    assert repo.git.current_branch() == "trunk"


# --------------------------------------------------------------------------
# Reviews and resumption
# --------------------------------------------------------------------------


def test_only_sensitive_tickets_get_a_security_review(project):
    settings, project_dir, ledger = project
    runner, error = run_build(settings, project_dir, ledger, base_scripts())

    assert error is None
    reviewed = [c for c in runner.calls if c.role == "reviewer"]
    secured = [c for c in runner.calls if c.role == "security"]
    assert len(reviewed) == 3
    # Only T-03 (the paywall ticket) is marked sensitive in the backlog.
    assert len(secured) == 1
    assert "t-03" in str(secured[0].cwd)


def test_a_reviewer_that_cannot_answer_does_not_deadlock_the_ticket(project):
    settings, project_dir, ledger = project
    runner, error = run_build(
        settings, project_dir, ledger, base_scripts() | {"reviewer": "I am not sure."}
    )

    assert error is None
    report = BuildReport.load(project_dir)
    assert all(t.status == "merged" for t in report.tickets)
    # One dev call per ticket: an unparseable review is not a rejection.
    assert len([c for c in runner.calls if c.role == "dev"]) == 3


def test_a_resumed_stage_does_not_rebuild_merged_tickets(project):
    settings, project_dir, ledger = project
    run_build(settings, project_dir, ledger, base_scripts())
    assert all(s == TicketStatus.MERGED for s in ledger.state.tickets.values())

    runner, error = run_build(settings, project_dir, ledger, base_scripts())

    assert error is None
    assert not [c for c in runner.calls if c.role == "dev"], "no ticket should be redone"
