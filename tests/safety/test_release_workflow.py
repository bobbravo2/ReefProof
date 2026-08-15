from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WORKFLOW = Path(".github/workflows/release.yml")


def test_release_quality_and_scan_gate_precede_publication() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    quality = workflow.index("quality:")
    publish = workflow.index("publish:")
    scan = workflow.index("name: Scan image for release-blocking vulnerabilities")
    push = workflow.index("name: Push verified image")

    assert quality < publish
    assert "needs: quality" in workflow[publish:scan]
    assert scan < push
    assert "push: true" not in workflow[:push]


def test_release_evidence_upload_runs_even_when_scan_fails() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    upload = workflow.index("name: Upload release evidence")
    next_step = workflow.index("name: Push verified image")

    assert "if: always()" in workflow[upload:next_step]


def test_release_uses_post_push_registry_digest_for_published_references() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    push = workflow.index("name: Push verified image")
    attestation = workflow.index("name: Attest image provenance")

    assert "RepoDigests" in workflow[push:attestation]
    assert "docker image inspect" in workflow[push:attestation]
    assert "steps.push.outputs.digest" in workflow[attestation:]
    assert "steps.build.outputs.digest" not in workflow[push:]
    assert workflow.index("name: Publish release receipt") > attestation
    assert "Deploy the immutable OCI digest above" in workflow


def test_release_actions_and_uv_are_immutably_pinned() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for line in workflow.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            reference = stripped.split("@", maxsplit=1)[1].split()[0]
            assert len(reference) == 40
            assert all(character in "0123456789abcdef" for character in reference)
    assert 'version: "0.11.32"' in workflow


def test_release_quality_gate_requires_tag_to_match_package_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    quality = workflow.index("name: exact-tag quality gate")
    tag_check = workflow.index("name: Verify release tag matches package version")
    publish = workflow.index("name: publish signed Linux amd64 image")

    assert quality < tag_check < publish
    assert 'scripts/verify-release-tag.py "$GITHUB_REF_NAME"' in workflow[tag_check:publish]


def test_release_tag_verifier_accepts_only_the_package_version() -> None:
    from reefproof import __version__

    matching = subprocess.run(
        [sys.executable, "scripts/verify-release-tag.py", f"v{__version__}"],
        check=False,
        capture_output=True,
        text=True,
    )
    mismatching = subprocess.run(
        [sys.executable, "scripts/verify-release-tag.py", "v999.0.0"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert matching.returncode == 0
    assert "PASS: release tag v0.1.1 matches package version 0.1.1" in matching.stdout
    assert mismatching.returncode == 2
    assert "does not match package version" in mismatching.stderr
