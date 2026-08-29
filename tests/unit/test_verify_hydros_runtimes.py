from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts/verify-hydros-runtimes.py"
RESULT = {
    "detailed_explanation": "The operator-confirmed display unit matches the export.",
    "evidence": ['$.Option["Option"].tempFmt = "1"'],
    "invariant_id": "RP-UNIT-001",
    "severity": "info",
    "snapshot_hash": "sha256:" + "a" * 64,
    "state": "PASS",
    "summary": "HYDROS temperature display format is Fahrenheit.",
}


def run_verifier(
    tmp_path: Path, *, mismatch: tuple[str, object] | None = None
) -> subprocess.CompletedProcess[str]:
    paths: dict[str, Path] = {}
    for runtime in ("source", "binary", "oci"):
        document = RESULT.copy()
        if runtime == "binary" and mismatch is not None:
            document[mismatch[0]] = mismatch[1]
        path = tmp_path / f"{runtime}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[runtime] = path
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--source-result",
            str(paths["source"]),
            "--binary-result",
            str(paths["binary"]),
            "--oci-result",
            str(paths["oci"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_runtime_parity_accepts_matching_release_evidence(tmp_path: Path) -> None:
    result = run_verifier(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: source, binary, and OCI offline HYDROS results match" in result.stdout


@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        ("detailed_explanation", "Different explanation."),
        ("evidence", ["different evidence"]),
        ("invariant_id", "RP-OTHER-999"),
        ("severity", "high"),
        ("snapshot_hash", "sha256:" + "b" * 64),
        ("state", "UNKNOWN"),
        ("summary", "Different summary."),
    ],
)
def test_runtime_parity_names_each_differing_field(
    tmp_path: Path, field: str, different_value: object
) -> None:
    result = run_verifier(tmp_path, mismatch=(field, different_value))
    assert result.returncode != 0
    assert f"binary runtime differs for {field}" in result.stderr
