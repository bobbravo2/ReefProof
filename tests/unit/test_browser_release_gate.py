from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bootstrap_installs_pinned_playwright_chromium_after_clean_npm_install() -> None:
    package = json.loads(_text("package.json"))
    bootstrap = _text("scripts/bootstrap.sh")

    assert package["devDependencies"]["@playwright/test"] == "1.55.0"
    assert package["scripts"]["browser:install"] == "playwright install chromium"
    assert bootstrap.index("npm ci") < bootstrap.index("npm run browser:install")
    assert bootstrap.index("npm run browser:install") < bootstrap.index("npm run build")


def test_clean_quality_and_release_paths_bootstrap_before_browser_gate() -> None:
    makefile = _text("Makefile")
    assert "test/check:" in makefile
    assert "\tnpm run test:browser\n" in makefile

    for workflow_path, job_name in (
        (".github/workflows/checks.yml", "check"),
        (".github/workflows/delivery.yml", "quality"),
        (".github/workflows/release.yml", "quality"),
    ):
        workflow = yaml.safe_load(_text(workflow_path))
        steps = workflow["jobs"][job_name]["steps"]
        commands = [step.get("run") for step in steps if "run" in step]
        assert commands.index("./scripts/bootstrap.sh") < commands.index("make check")
