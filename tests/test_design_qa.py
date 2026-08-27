"""Stage 65: the app is rendered, measured and looked at.

The screenshot pipeline is stubbed with a script that emits canned probe output,
so these cover the orchestration - findings becoming tickets, tickets going
through the build loop, re-capture after a fix - without an Expo export. One
opt-in test runs the real thing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from textwrap import dedent

import fixtures as fx
import pytest

from shipyard.config import Settings
from shipyard.contracts import BuildReport, DesignQAReport, TicketOutcome
from shipyard.ledger import Ledger
from shipyard.pipeline import build_context
from shipyard.pipeline.design_qa import DesignQA, DesignQAConfig, web_route
from shipyard.pipeline.tickets import BuildConfig
from shipyard.runner import RoleRequest, ScriptedRunner
from shipyard.verify import Check
from shipyard.workspace import AppRepo, create_project

REPO_ROOT = Path(__file__).parent.parent

PASS = fx.PASS_VERDICT
LOOKS_WRONG = json.dumps(
    {
        "verdict": "fail",
        "summary": "the history rows read as one block",
        "findings": [
            {
                "severity": "blocking",
                "where": "/history",
                "problem": "row title and timestamp are 4px apart while rows are 16px apart",
                "fix": "raise the gap between rows to 16px or tighten the intra-row gap",
            }
        ],
    }
)

TAP_TARGET = [
    {
        "route": "/",
        "viewport": "iphone",
        "kind": "touch_target",
        "label": "Filter",
        "detail": "32x32px is below 44px",
    }
]
SERIOUS_A11Y = [
    {
        "route": "/paywall",
        "id": "document-title",
        "impact": "serious",
        "help": "Documents must have <title> element",
        "nodes": ["<html>"],
    }
]
MINOR_A11Y = [
    {"route": "/", "id": "region", "impact": "minor", "help": "All content should be in landmarks", "nodes": []}
]


def suite(directory: Path) -> list[Check]:
    return [Check("suite", "test ! -f BROKEN", directory, 30)]


def stub_screenshots(tmp_path: Path, rounds: list[tuple[list, list]]) -> str:
    """A stand-in for `screenshots.mjs` that emits canned probe output.

    Each invocation consumes the next entry, so a test can say "dirty, then
    clean" and exercise the re-capture after a fix.
    """
    script = tmp_path / "stub_screenshots.py"
    script.write_text(
        dedent(
            f"""
            import json, pathlib, sys
            rounds = json.loads({json.dumps(json.dumps(rounds))})
            out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
            counter = out.parent / ".stub-count"
            n = int(counter.read_text()) if counter.exists() else 0
            counter.parent.mkdir(parents=True, exist_ok=True)
            counter.write_text(str(n + 1))
            a11y, layout = rounds[min(n, len(rounds) - 1)]
            (out / "screens").mkdir(parents=True, exist_ok=True)
            for name in ("home.iphone", "home.android", "gallery.iphone"):
                (out / "screens" / (name + ".png")).write_bytes(b"\\x89PNG\\r\\n\\x1a\\n")
            (out / "a11y.json").write_text(json.dumps(a11y))
            (out / "layout.json").write_text(json.dumps(layout))
            serious = [v for v in a11y if v.get("impact") in ("serious", "critical")]
            sys.exit(1 if serious or layout else 0)
            """
        )
    )
    return f"python3 {script} --out {{out}} --routes {{routes}}"


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

    # Stage 65 runs against an app that stage 60 already built.
    repo = AppRepo.from_template(settings.templates_dir / "expo-app", project_dir / "app")
    BuildReport(
        trunk_commit=repo.git.head(),
        tickets=[TicketOutcome(id="T-01", status="merged")],
        checks="PASS",
    ).save(project_dir)
    return settings, project_dir, ledger


def drive(settings, project_dir, ledger, scripts, config):
    runner = ScriptedRunner(scripts)
    ctx = build_context(project_dir, ledger, runner, settings)
    error: Exception | None = None
    try:
        asyncio.run(DesignQA(config).execute(ctx))
    except Exception as exc:
        error = exc
    return runner, error


def base_scripts() -> dict:
    def dev(req: RoleRequest) -> str:
        target = Path(req.cwd) / "src" / "ui" / "fix.ts"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"export const fixed = '{Path(req.cwd).name}';\n")
        return "fixed it"

    return {"design_qa": PASS, "s65_design_qa:dev": dev, "reviewer": PASS, "security": PASS}


# --------------------------------------------------------------------------


def test_expo_routes_become_the_urls_the_web_export_serves():
    assert web_route("/(tabs)/index") == "/"
    assert web_route("/(tabs)/history") == "/history"
    assert web_route("/(app)/(tabs)/settings") == "/settings"
    assert web_route("/paywall") == "/paywall"
    # A dynamic route cannot be rendered without data, so it is not photographed.
    assert web_route("/item/[id]") is None


def test_a_clean_app_passes_without_touching_any_code(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [([], [])]),
    )

    runner, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is None
    report = DesignQAReport.load(project_dir)
    assert report.verdict == "pass"
    assert report.a11y_violations == 0 and report.layout_findings == 0
    assert report.screenshots and all(s.startswith("qa/screens/") for s in report.screenshots)
    assert not [c for c in runner.calls if c.role == "dev"], "nothing needed fixing"


def test_every_renderable_screen_plus_the_gallery_is_photographed(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite), screenshots_cmd=stub_screenshots(tmp_path, [([], [])])
    )

    drive(settings, project_dir, ledger, base_scripts(), config)

    report = DesignQAReport.load(project_dir)
    # The fixture's three screens, plus the component gallery.
    assert report.routes == ["/", "/history", "/paywall", "/__gallery"]


def test_the_reviewer_is_pointed_at_the_actual_images(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite), screenshots_cmd=stub_screenshots(tmp_path, [([], [])])
    )

    runner, _ = drive(settings, project_dir, ledger, base_scripts(), config)

    task = " ".join(next(c.task for c in runner.calls if c.role == "design_qa").split())
    assert "read every one of these images" in task
    assert "home.iphone.png" in task and "gallery.iphone.png" in task
    # It must not waste its judgement re-reporting what the probes measured.
    assert "Do not repeat them" in task
    assert "Report what a machine cannot see" in task


def test_a_measured_layout_defect_becomes_a_fix_ticket(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [([], TAP_TARGET), ([], [])]),
    )

    runner, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is None
    dev_calls = [c for c in runner.calls if c.role == "dev"]
    assert len(dev_calls) == 1
    assert "32x32px is below 44px" in dev_calls[0].task
    assert "do not weaken the checks" in dev_calls[0].task.lower()

    report = DesignQAReport.load(project_dir)
    assert report.verdict == "pass"
    assert [f.status for f in report.fixes] == ["merged"]


def test_a_minor_accessibility_violation_does_not_cost_a_build_cycle(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [(MINOR_A11Y, [])]),
    )

    runner, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is None
    assert not [c for c in runner.calls if c.role == "dev"]
    assert DesignQAReport.load(project_dir).verdict == "pass"


def test_a_serious_accessibility_violation_becomes_a_fix_ticket(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [(SERIOUS_A11Y, []), ([], [])]),
    )

    runner, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is None
    dev_calls = [c for c in runner.calls if c.role == "dev"]
    assert len(dev_calls) == 1
    assert "document-title" in dev_calls[0].task
    assert DesignQAReport.load(project_dir).verdict == "pass"


def test_a_finding_only_a_human_eye_would_catch_also_becomes_a_ticket(project, tmp_path):
    settings, project_dir, ledger = project
    verdicts = iter([LOOKS_WRONG])
    scripts = base_scripts() | {"design_qa": lambda req: next(verdicts, PASS)}
    config = DesignQAConfig(
        build=BuildConfig(checks=suite), screenshots_cmd=stub_screenshots(tmp_path, [([], [])])
    )

    runner, error = drive(settings, project_dir, ledger, scripts, config)

    assert error is None
    dev_calls = [c for c in runner.calls if c.role == "dev"]
    assert len(dev_calls) == 1
    assert "4px apart while rows are 16px apart" in dev_calls[0].task


def test_design_fixes_go_through_code_review_like_any_other_change(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [([], TAP_TARGET), ([], [])]),
    )

    runner, _ = drive(settings, project_dir, ledger, base_scripts(), config)

    assert [c.role for c in runner.calls if c.role == "reviewer"], "a design fix skipped review"
    repo = AppRepo.open(project_dir / "app")
    assert not repo.git.is_dirty()
    assert (repo.root / "src" / "ui" / "fix.ts").is_file(), "the fix never reached trunk"


def test_defects_that_survive_every_fix_round_fail_the_stage(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd=stub_screenshots(tmp_path, [([], TAP_TARGET)]),
        max_fix_rounds=2,
    )

    runner, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is not None
    assert "survived 2 fix rounds" in str(error)
    report = DesignQAReport.load(project_dir)
    assert report.verdict == "fail"
    assert report.blocking
    assert len(report.fixes) == 2, "one fix attempt per round"


def test_a_broken_render_is_not_reported_as_a_design_defect(project, tmp_path):
    settings, project_dir, ledger = project
    config = DesignQAConfig(
        build=BuildConfig(checks=suite),
        screenshots_cmd="python3 -c 'import sys; sys.exit(2)' {out} {routes}",
    )

    _, error = drive(settings, project_dir, ledger, base_scripts(), config)

    assert error is not None
    assert "could not render the app" in str(error)


def test_an_unreadable_design_verdict_does_not_deadlock_the_stage(project, tmp_path):
    settings, project_dir, ledger = project
    scripts = base_scripts() | {"design_qa": "I could not decide."}
    config = DesignQAConfig(
        build=BuildConfig(checks=suite), screenshots_cmd=stub_screenshots(tmp_path, [([], [])])
    )

    _, error = drive(settings, project_dir, ledger, scripts, config)

    assert error is None
    report = DesignQAReport.load(project_dir)
    assert report.verdict == "pass"
    assert "measured checks stand alone" in report.summary
