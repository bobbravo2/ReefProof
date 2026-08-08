from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from reefproof import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
DISPLAY_IDENTITY = f"ReefProof {__version__}"
FIXTURE_VERSION = "0.69.420"


def run_make(
    repo: Path, *targets: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["make", *targets]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        command, cwd=repo, check=False, capture_output=True, text=True, env=merged_env
    )


def run_python(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def project_version(project_file: Path) -> str:
    return tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]["version"]


def write_minimal_build_repo(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(
        f'[project]\nversion = "{FIXTURE_VERSION}"\n',
        encoding="utf-8",
    )
    shutil.copy2(MAKEFILE, repo / "Makefile")
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Codex"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "codex@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "add", "Makefile", "pyproject.toml"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True, text=True
    )


def test_make_help_lists_primary_workflows_and_domains() -> None:
    result = run_make(REPO_ROOT, "help")

    assert result.returncode == 0, result.stdout + result.stderr
    for expected in (
        "make setup",
        "make run",
        "make test",
        "make build",
        "make check",
        "make clean",
        "make setup/help",
        "make run/help",
        "make test/help",
        "make build/help",
        "make ops/help",
        "make agent/help",
    ):
        assert expected in result.stdout
    assert DISPLAY_IDENTITY in result.stdout


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("setup/help", "setup domain"),
        ("run/help", "run domain"),
        ("test/help", "test domain"),
        ("build/help", "build domain"),
        ("ops/help", "ops domain"),
        ("agent/help", "agent domain"),
    ],
)
def test_domain_help_targets_exist(target: str, expected: str) -> None:
    result = run_make(REPO_ROOT, target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert expected in result.stdout


def test_build_targets_print_copy_pasteable_runtime_steps() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "Next steps:" in makefile
    assert "./dist/reefproof version" in makefile
    assert "./dist/reefproof doctor" in makefile
    assert "./dist/reefproof infra-smoke --format json" in makefile
    assert "$(CONTAINER_TOOL) run --rm --read-only --network=none" in makefile
    assert "reefproof:build-" in makefile
    assert "$(CONTAINER_TOOL)" in makefile


def test_top_level_aliases_delegate_to_domain_targets() -> None:
    # Ensure that the toplevel ReefProof v0.1 Makefile contract follows the SDLC
    makefile = MAKEFILE.read_text(encoding="utf-8")

    for expected in (
        r"^setup:\s+setup/bootstrap$",
        r"^run:\s+run/help$",
        r"^test:\s+test/check$",
        r"^check:\s+test/check$",
        r"^clean:\s+build/clean$",
    ):
        assert re.search(expected, makefile, re.MULTILINE), expected


def test_build_preflight_rejects_dirty_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    write_minimal_build_repo(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    failure = run_make(repo, "build/preflight")
    assert failure.returncode == 2
    assert "refusing to package a dirty working tree" in failure.stderr


def test_build_stage_excludes_sensitive_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "README.md").write_text("ReefProof\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f'[project]\nversion = "{FIXTURE_VERSION}"\n',
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text("lock\n", encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / ".dockerignore").write_text(".local\n", encoding="utf-8")

    (repo / "src/reefproof").mkdir(parents=True)
    (repo / "src/reefproof/__init__.py").write_text(
        '"""reefproof"""\n',
        encoding="utf-8",
    )

    (repo / "scripts").mkdir()
    (repo / "scripts/write-build-identity.py").write_text(
        "#!/usr/bin/env python3\n",
        encoding="utf-8",
    )

    for excluded in (
        ".local/private.json",
        "captures/raw.log",
        "secrets/token.txt",
        "config/reefproof.yaml",
        "build/cache.tmp",
    ):
        path = repo / excluded
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("excluded\n", encoding="utf-8")

    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            "--",
            ".dockerignore",
            "Dockerfile",
            "README.md",
            "pyproject.toml",
            "uv.lock",
            "src/reefproof/__init__.py",
            "scripts/write-build-identity.py",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    result = run_python(
        "scripts/build-stage.py",
        "--repo",
        str(repo),
        "--output",
        ".build/stage",
        cwd=repo,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    staged = repo / ".build/stage"

    for expected in (
        ".dockerignore",
        "Dockerfile",
        "README.md",
        "pyproject.toml",
        "uv.lock",
        "src/reefproof/__init__.py",
        "scripts/write-build-identity.py",
    ):
        assert (staged / expected).is_file(), expected

    for excluded in (
        ".local",
        "captures",
        "secrets",
        "config",
        "build",
    ):
        assert not (staged / excluded).exists(), excluded


def test_build_manifest_checksums_and_verify_bundle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    dist = repo / "dist"
    dist.mkdir(parents=True)

    (repo / "pyproject.toml").write_text(
        f'[project]\nversion = "{FIXTURE_VERSION}"\n',
        encoding="utf-8",
    )

    fixture_version = project_version(repo / "pyproject.toml")
    fixture_identity = f"ReefProof {fixture_version}"
    fixture_source = "https://github.com/bobbravo2/ReefProof"
    fixture_revision = "abc123"
    fixture_created = "2026-07-26T12:00:00Z"
    archive_name = f"reefproof-{fixture_version}-linux-amd64.tar.gz"

    (dist / "reefproof").write_text("binary\n", encoding="utf-8")
    (dist / archive_name).write_text("archive\n", encoding="utf-8")

    receipt = [
        {
            "Config": {
                "Entrypoint": ["reefproof"],
                "Env": ["REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof"],
                "Labels": {
                    "org.opencontainers.image.revision": fixture_revision,
                    "org.opencontainers.image.source": fixture_source,
                    "org.opencontainers.image.title": "ReefProof",
                    "org.opencontainers.image.version": fixture_version,
                },
            }
        }
    ]
    (dist / "reefproof-image.json").write_text(
        json.dumps(receipt),
        encoding="utf-8",
    )

    sbom = run_python(
        "scripts/build-sbom.py",
        "--output",
        "dist/reefproof.spdx.json",
        "--product-name",
        "ReefProof",
        "--version",
        fixture_version,
        "--revision",
        fixture_revision,
        "--source",
        fixture_source,
        "--created",
        fixture_created,
        "--root",
        "dist",
        "reefproof",
        archive_name,
        "reefproof-image.json",
        cwd=repo,
    )
    assert sbom.returncode == 0, sbom.stdout + sbom.stderr

    sbom_document = json.loads((dist / "reefproof.spdx.json").read_text(encoding="utf-8"))
    assert sbom_document["spdxVersion"] == "SPDX-2.3"
    assert {entry["fileName"].removeprefix("./") for entry in sbom_document["files"]} == {
        "reefproof",
        archive_name,
        "reefproof-image.json",
    }

    manifest = run_python(
        "scripts/build-manifest.py",
        "--output",
        "dist/build-manifest.json",
        "--product-name",
        "ReefProof",
        "--version",
        fixture_version,
        "--display-identity",
        fixture_identity,
        "--revision",
        fixture_revision,
        "--source",
        fixture_source,
        "--created",
        fixture_created,
        "--entrypoint",
        "reefproof",
        "--data-directory",
        "/var/lib/reefproof",
        "--root",
        "dist",
        "reefproof",
        archive_name,
        "reefproof-image.json",
        "reefproof.spdx.json",
        cwd=repo,
    )
    assert manifest.returncode == 0, manifest.stdout + manifest.stderr

    manifest_document = json.loads((dist / "build-manifest.json").read_text(encoding="utf-8"))
    assert manifest_document["product"]["display_identity"] == fixture_identity
    assert {entry["name"] for entry in manifest_document["artifacts"]} == {
        "reefproof",
        archive_name,
        "reefproof-image.json",
        "reefproof.spdx.json",
    }

    checksums = run_python(
        "scripts/build-checksums.py",
        "--root",
        "dist",
        "--output",
        "dist/SHA256SUMS",
        "reefproof",
        archive_name,
        "reefproof-image.json",
        "reefproof.spdx.json",
        "build-manifest.json",
        cwd=repo,
    )
    assert checksums.returncode == 0, checksums.stdout + checksums.stderr

    verify = run_python(
        "scripts/build-verify.py",
        "--root",
        "dist",
        "--checksums",
        "SHA256SUMS",
        "--manifest",
        "build-manifest.json",
        "--sbom",
        "reefproof.spdx.json",
        "--image-receipt",
        "reefproof-image.json",
        "--binary",
        "reefproof",
        cwd=repo,
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_agent_evaluation_is_not_in_test_build_or_ci_graphs() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    for section in ("test/check:", "build/delivery:"):
        assert section in makefile
        window = makefile.split(section, maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
        assert "agent/eval" not in window
    for workflow_name in ("checks.yml", "delivery.yml", "release.yml"):
        workflow = (REPO_ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
        assert "agent/eval" not in workflow
        assert "benchmark" not in workflow or workflow_name == "release.yml"


def test_build_delivery_section_stays_local_only() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    section = makefile.split("build/delivery:", maxsplit=1)[1].split("ops/help:", maxsplit=1)[0]
    for forbidden in ("push", "publish", "deploy"):
        assert forbidden not in section
