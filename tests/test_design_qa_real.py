"""One real render: export the app to web, drive a real browser, measure it.

Slow (a few minutes, installs node_modules and bundles the app), so it is
opt-in:

    SHIPYARD_SLOW_TESTS=1 pytest tests/test_design_qa_real.py

The fast tests stub the screenshot pipeline. This one covers what they
deliberately stub: that `expo export` really produces a static web build, that
Playwright really drives it, and that the template really has no serious
accessibility violation or layout defect.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import fixtures as fx
import pytest

from shipyard.config import Settings
from shipyard.contracts import BuildReport, TicketOutcome, UXSpec
from shipyard.ledger import Ledger
from shipyard.pipeline import build_context
from shipyard.pipeline.design_qa import DesignQA, DesignQAConfig
from shipyard.pipeline.tickets import BuildConfig, scaffold_app
from shipyard.runner import ScriptedRunner
from shipyard.workspace import create_project

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    os.environ.get("SHIPYARD_SLOW_TESTS") != "1",
    reason="set SHIPYARD_SLOW_TESTS=1 to run the real browser render",
)


def test_the_template_renders_clean_under_a_real_browser(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        projects_dir=tmp_path / "projects",
        templates_dir=REPO_ROOT / "templates",
        prompts_dir=REPO_ROOT / "prompts",
    )
    project_dir = create_project(settings.projects_dir, "tip-splitter")
    fx.full_project(project_dir)
    ledger = Ledger.create(project_dir, "tip-splitter", "Tip Splitter")

    runner = ScriptedRunner({"design_qa": fx.PASS_VERDICT})
    ctx = build_context(project_dir, ledger, runner, settings)

    build = BuildConfig()
    repo = scaffold_app(ctx, build, "s60_build")
    BuildReport(
        trunk_commit=repo.git.head(),
        tickets=[TicketOutcome(id="T-01", status="merged")],
        checks="PASS",
    ).save(project_dir)

    stage = DesignQA(DesignQAConfig(build=build))
    routes = stage._routes(UXSpec.load(project_dir))
    qa = project_dir / "qa"
    stage._capture(ctx, routes, qa)

    # Both viewports, every route, plus the component gallery.
    screens = sorted(p.name for p in (qa / "screens").glob("*.png"))
    for expected in ("home.iphone.png", "home.android.png", "gallery.iphone.png",
                     "gallery.android.png", "paywall.iphone.png"):
        assert expected in screens, f"{expected} was not captured"
    assert all((qa / "screens" / name).stat().st_size > 1000 for name in screens)

    layout = json.loads((qa / "layout.json").read_text())
    a11y = json.loads((qa / "a11y.json").read_text())
    serious = [v for v in a11y if v["impact"] in ("serious", "critical")]

    # The template itself must ship clean under real measurement.
    assert serious == [], f"the template ships with accessibility violations: {serious}"
    measured = [f for f in layout if f["kind"] != "route_missing"]
    assert measured == [], f"the template ships with layout defects: {measured}"

    # The fixture's UX spec declares /history, which the starter app does not
    # implement. That is a real gap and the stage must name it as one rather
    # than measuring Expo's not-found page and blaming the design system.
    missing = {f["route"] for f in layout if f["kind"] == "route_missing"}
    assert missing == {"/history"}
