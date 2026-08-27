"""The golden template must stay in sync with the contracts that feed it.

These are cheap structural checks. The template's own behaviour is covered by
its Jest suite, run via `templates/expo-app/scripts/verify.sh`.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import fixtures as fx
import pytest

from shipyard.config import load_settings
from shipyard.contracts import MonetizationPlan

TEMPLATE = load_settings().templates_dir / "expo-app"


def test_template_exists_with_the_files_the_pipeline_relies_on():
    for rel in (
        "package.json",
        "package-lock.json",
        "app.config.ts",
        "product.json",
        "monetization.json",
        "eas.json",
        ".env.example",
        "scripts/verify.sh",
        "scripts/apply-product.mjs",
        "src/purchases/entitlements.tsx",
        "src/config/monetization.ts",
        "src/theme/tokens.generated.ts",
    ):
        assert (TEMPLATE / rel).is_file(), f"template is missing {rel}"


def test_template_monetization_satisfies_the_pipeline_contract():
    """The app parses the same file the monetization role writes, so the two
    definitions of a plan must not drift."""
    MonetizationPlan.model_validate_json((TEMPLATE / "monetization.json").read_text())


def test_verify_script_runs_every_check_the_pipeline_expects():
    script = (TEMPLATE / "scripts" / "verify.sh").read_text()
    for check in ("typecheck", "lint", "format", "test"):
        assert re.search(rf"^run {check}\b", script, re.MULTILINE), f"verify.sh omits {check}"


def test_package_scripts_exist_for_every_check():
    scripts = json.loads((TEMPLATE / "package.json").read_text())["scripts"]
    for name in ("typecheck", "lint", "format:check", "test", "verify", "apply-product"):
        assert name in scripts, f"package.json has no '{name}' script"


def test_env_example_carries_no_real_secrets():
    body = (TEMPLATE / ".env.example").read_text()
    for line in body.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            # Only a documented default host may carry a value.
            assert value.strip() in ("", "https://us.i.posthog.com"), (
                f"{key} ships a value; .env.example must be blank"
            )
        assert "service_role" not in line.lower()


def test_apply_product_projects_artifacts_into_a_runnable_app(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    fx.idea().save(project)
    fx.design().save(project)
    fx.monetization().save(project)

    app = tmp_path / "app"
    subprocess.run(
        ["cp", "-r", str(TEMPLATE), str(app)], check=True, capture_output=True
    )
    result = subprocess.run(
        ["node", "scripts/apply-product.mjs", "--project", str(project)],
        cwd=app,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    product = json.loads((app / "product.json").read_text())
    design = fx.design()
    assert product["name"] == design.app_name
    assert product["slug"] == fx.idea().slug
    assert product["bundleId"] == "com.shipyard.tipsplitter"
    # A different product starts its own version history.
    assert product["version"] == "1.0.0"
    assert product["buildNumber"] == 1

    tokens = (app / "src" / "theme" / "tokens.generated.ts").read_text()
    assert design.tokens.color_primary in tokens
    assert f"radius: {design.tokens.radius}" in tokens

    # The plan reaches the app byte-identical, so the app and the pipeline agree.
    assert json.loads((app / "monetization.json").read_text()) == json.loads(
        (project / "monetization.json").read_text()
    )

    # The paywall E2E flow asserts against the allowance the plan specifies.
    paywall = (app / "maestro" / "paywall.yaml").read_text()
    assert "appId: com.shipyard.tipsplitter" in paywall
    assert "times: 5" in paywall


def test_apply_product_fails_loudly_on_a_missing_project(tmp_path: Path):
    result = subprocess.run(
        ["node", str(TEMPLATE / "scripts" / "apply-product.mjs"), "--project", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "cannot read" in result.stderr


@pytest.mark.parametrize("forbidden", ["EXPO_PUBLIC_SUPABASE_SERVICE", "SERVICE_ROLE"])
def test_no_server_side_credentials_are_referenced_in_app_source(forbidden: str):
    for path in (TEMPLATE / "src").rglob("*.ts*"):
        assert forbidden not in path.read_text(), f"{path} references {forbidden}"
