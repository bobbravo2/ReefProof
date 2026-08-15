from __future__ import annotations

import subprocess
from pathlib import Path

from reefproof import __version__


def test_package_version_matches_project_metadata() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert f'version = "{__version__}"' in pyproject


def test_binary_build_uses_isolated_source_and_verifies_artifact() -> None:
    result = subprocess.run(
        ["make", "-B", "-n", "build/binary"],
        # cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scripts/build-stage.py" in result.stdout
    assert "scripts/build-binary.sh" in result.stdout
    assert result.stdout.index("scripts/build-stage.py") < result.stdout.index(
        "scripts/build-binary.sh"
    )

    build_script = Path("scripts/build-binary.sh").read_text(encoding="utf-8")
    verifier = Path("scripts/verify-binary.sh").read_text(encoding="utf-8")
    assert "./scripts/verify-binary.sh" in build_script
    assert "--no-dev" in build_script
    assert "--group build" in build_script
    assert "--no-editable" in build_script
    assert "--hidden-import _scproxy" in build_script
    assert "--collect-submodules reefproof" in build_script
    assert 'grep -Fq "database" "$execution_root/help.txt"' in verifier
    assert 'grep -Fq "storage" "$execution_root/help.txt"' not in verifier


def test_delivery_evaluations_use_canonical_make_targets() -> None:
    registry = Path(".agent/evals.yaml").read_text(encoding="utf-8")

    assert "command: make build/binary" in registry
    assert "command: make build/container" in registry
    assert "command: make binary\n" not in registry
    assert "command: podman build" not in registry


def test_docker_context_excludes_local_and_private_state() -> None:
    exclusions = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())
    required = {
        ".agent",
        ".codex",
        ".env",
        ".env.*",
        ".git",
        ".local",
        ".venv",
        "build",
        "captures",
        "config",
        "dist",
        "docs",
        "secrets",
        "tests",
    }

    assert required <= exclusions


def test_container_removes_local_install_metadata() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    build_script = Path("scripts/build-container.sh").read_text(encoding="utf-8")

    assert "-name direct_url.json" in dockerfile
    assert "-name uv_cache.json" in dockerfile
    assert dockerfile.count("python:3.13-alpine@sha256:") == 2
    assert "ghcr.io/astral-sh/uv:0.11.32@sha256:" in dockerfile
    assert "http://127.0.0.1:18787/assets/workbench.js" in build_script
    assert 'grep -Fq "const API_ROOT" /tmp/workbench.js' in build_script


def test_all_workflow_actions_are_immutably_pinned() -> None:
    for workflow_path in Path(".github/workflows").glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        for line in workflow.splitlines():
            stripped = line.strip()
            if stripped.startswith("- uses:") or stripped.startswith("uses:"):
                reference = stripped.split("@", maxsplit=1)[1].split()[0]
                assert len(reference) == 40, workflow_path
                assert all(character in "0123456789abcdef" for character in reference), (
                    workflow_path
                )


def test_workflow_actions_use_node_24_capable_releases() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(".github/workflows").glob("*.yml")
    )
    required_releases = {
        "actions/checkout": "# v7.0.1",
        "actions/setup-python": "# v7.0.0",
        "actions/setup-node": "# v7.0.0",
        "actions/upload-artifact": "# v7.0.1",
        "astral-sh/setup-uv": "# v9.0.0",
        "docker/login-action": "# v4.6.0",
        "docker/setup-buildx-action": "# v4.2.0",
        "docker/metadata-action": "# v6.2.0",
        "docker/build-push-action": "# v7.3.0",
    }

    for action, release in required_releases.items():
        matching_lines = [line for line in workflows.splitlines() if f"uses: {action}@" in line]
        assert matching_lines, action
        assert all(line.endswith(release) for line in matching_lines), (action, matching_lines)


def test_uv_caches_are_isolated_between_concurrent_workflow_jobs() -> None:
    workflows = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(".github/workflows").glob("*.yml")
    )
    setup_count = workflows.count("uses: astral-sh/setup-uv@")
    suffixes = {
        line.split(":", maxsplit=1)[1].strip()
        for line in workflows.splitlines()
        if line.strip().startswith("cache-suffix:")
    }

    assert setup_count == 5
    assert len(suffixes) == setup_count
