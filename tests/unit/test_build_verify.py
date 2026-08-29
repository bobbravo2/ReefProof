from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts/build-verify.py"
EXPECTED_IDENTITY = "ReefProof 9.8.7"
EXPECTED_REVISION = "a" * 40


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bundle(
    root: Path,
    *,
    display_identity: str = EXPECTED_IDENTITY,
    revision: str = EXPECTED_REVISION,
    container_user: str = "reefproof",
    default_command: list[str] | None = None,
) -> None:
    archive_name = "reefproof-9.8.7-linux-amd64.tar.gz"
    (root / "reefproof").write_bytes(b"binary\n")
    (root / archive_name).write_bytes(b"archive\n")
    receipt = [
        {
            "Config": {
                "Cmd": default_command if default_command is not None else ["version"],
                "Entrypoint": ["reefproof"],
                "Env": ["REEFPROOF_DATA_DIRECTORY=/var/lib/reefproof"],
                "Labels": {
                    "org.opencontainers.image.revision": revision,
                    "org.opencontainers.image.source": "https://example.test/ReefProof",
                    "org.opencontainers.image.title": "ReefProof",
                    "org.opencontainers.image.version": "9.8.7",
                },
                "User": container_user,
            }
        }
    ]
    (root / "reefproof-image.json").write_text(json.dumps(receipt), encoding="utf-8")
    sbom_files = ["reefproof", archive_name, "reefproof-image.json"]
    sbom = {"spdxVersion": "SPDX-2.3", "files": [{"fileName": f"./{name}"} for name in sbom_files]}
    (root / "reefproof.spdx.json").write_text(json.dumps(sbom), encoding="utf-8")
    artifact_names = [*sbom_files, "reefproof.spdx.json"]
    manifest = {
        "schema_version": 1,
        "artifacts": [
            {
                "name": name,
                "path": name,
                "sha256": sha256(root / name),
                "size": (root / name).stat().st_size,
            }
            for name in artifact_names
        ],
        "product": {"display_identity": display_identity, "name": "ReefProof", "version": "9.8.7"},
        "runtime": {"data_directory": "/var/lib/reefproof", "entrypoint": "reefproof"},
        "source": {
            "created": "2026-08-16T00:00:00Z",
            "revision": revision,
            "url": "https://example.test/ReefProof",
        },
    }
    (root / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    checksum_names = [*artifact_names, "build-manifest.json"]
    (root / "SHA256SUMS").write_text(
        "".join(f"{sha256(root / name)}  {name}\n" for name in checksum_names), encoding="utf-8"
    )


def verify(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--root",
            str(root),
            "--expected-display-identity",
            EXPECTED_IDENTITY,
            "--expected-revision",
            EXPECTED_REVISION,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_candidate_bundle_contract_passes(tmp_path: Path) -> None:
    write_bundle(tmp_path)
    result = verify(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: verified 5 checksum(s) and build metadata" in result.stdout


def test_candidate_bundle_rejects_wrong_display_identity(tmp_path: Path) -> None:
    write_bundle(tmp_path, display_identity="ReefProof 9.8.8")
    result = verify(tmp_path)
    assert result.returncode != 0
    assert "display identity does not match expected candidate identity" in result.stderr


def test_candidate_bundle_rejects_wrong_source_revision(tmp_path: Path) -> None:
    write_bundle(tmp_path, revision="b" * 40)
    result = verify(tmp_path)
    assert result.returncode != 0
    assert "source revision does not match expected candidate revision" in result.stderr


def test_candidate_bundle_rejects_root_container_user(tmp_path: Path) -> None:
    write_bundle(tmp_path, container_user="0")
    result = verify(tmp_path)
    assert result.returncode != 0
    assert "container receipt configures a root user" in result.stderr


def test_candidate_bundle_rejects_unexpected_default_command(tmp_path: Path) -> None:
    write_bundle(tmp_path, default_command=["doctor"])
    result = verify(tmp_path)
    assert result.returncode != 0
    assert "container receipt default command is not one-shot version" in result.stderr
