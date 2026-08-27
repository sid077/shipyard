"""One end-to-end build against the real template, real npm, real checks.

Slow (a few minutes, and it installs node_modules), so it is opt-in:

    SHIPYARD_SLOW_TESTS=1 pytest tests/test_build_real.py

The fast build tests cover orchestration with stub commands. This one covers
what they deliberately stub: that the template really scaffolds, that
`apply-product.mjs` really runs, that `npm ci` really installs, and that a
ticket's change really passes typecheck, lint, formatting and Jest.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import fixtures as fx
import pytest

from shipyard.config import Settings
from shipyard.contracts import BuildReport
from shipyard.ledger import Ledger
from shipyard.pipeline import build_context
from shipyard.pipeline.build import Build, BuildConfig
from shipyard.runner import RoleRequest, ScriptedRunner
from shipyard.workspace import AppRepo, create_project

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    os.environ.get("SHIPYARD_SLOW_TESTS") != "1",
    reason="set SHIPYARD_SLOW_TESTS=1 to run the real npm build",
)


def real_dev(req: RoleRequest) -> str:
    """Add a genuinely type-checked, lint-clean, formatted module and its test."""
    cwd = Path(req.cwd)
    name = cwd.name.replace("-", "_")

    module = cwd / "src" / "features" / f"{name}.ts"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(
        "export function describeTicket(id: string): string {\n"
        "  return `implemented ${id}`;\n"
        "}\n"
    )

    spec = cwd / "__tests__" / f"{name}.test.ts"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        f"import {{ describeTicket }} from '@/features/{name}';\n"
        "\n"
        f"it('describes {cwd.name}', () => {{\n"
        f"  expect(describeTicket('{cwd.name}')).toBe('implemented {cwd.name}');\n"
        "});\n"
    )
    return f"added src/features/{name}.ts and its test"


def test_a_real_backlog_builds_a_green_app(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        projects_dir=tmp_path / "projects",
        templates_dir=REPO_ROOT / "templates",
        prompts_dir=REPO_ROOT / "prompts",
        build_concurrency=2,
    )
    project_dir = create_project(settings.projects_dir, "tip-splitter")
    fx.full_project(project_dir)
    ledger = Ledger.create(project_dir, "tip-splitter", "Tip Splitter")

    runner = ScriptedRunner(
        {"s60_build:dev": real_dev, "reviewer": fx.PASS_VERDICT, "security": fx.PASS_VERDICT}
    )
    ctx = build_context(project_dir, ledger, runner, settings)
    asyncio.run(Build(BuildConfig(concurrency=2)).execute(ctx))

    report = BuildReport.load(project_dir)
    assert all(t.status == "merged" for t in report.tickets)
    assert "PASS typecheck" in report.checks
    assert "PASS lint" in report.checks
    assert "PASS unit" in report.checks

    app = project_dir / "app"
    repo = AppRepo.open(app)
    assert not repo.git.is_dirty()
    # The product config was really applied to the shipped app.
    assert fx.design().app_name in (app / "product.json").read_text()
    for ticket in ("t_01", "t_02", "t_03"):
        assert (app / "src" / "features" / f"{ticket}.ts").is_file()
