from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(".codex/skills/reefproof-cli-startup-benchmark/scripts/benchmark.py")


def test_benchmark_records_multiple_successful_runs(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--runs",
            "2",
            "--warmups",
            "1",
            "--label",
            "test-command",
            "--expect",
            "ready",
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "print('ready')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.startswith("PASS label=test-command runs=2 warmups=1")
    result = json.loads(output.read_text())
    assert result["schema_version"] == 2
    assert result["command"] == [sys.executable, "-c", "print('ready')"]
    assert result["command_identity"]["sha256"]
    assert len(result["samples_ms"]) == 2
    assert len(result["measurements"]) == 2
    assert result["measurements"][0]["stdout_bytes"] == len("ready\n")
    assert len(result["measurements"][0]["stdout_sha256"]) == 64
    assert result["output_stable"] is True
    assert result["threshold_passed"] is True
    assert result["summary_ms"]["min"] <= result["summary_ms"]["median"]
    assert result["summary_ms"]["median"] <= result["summary_ms"]["max"]


def test_benchmark_rejects_a_failing_command_without_writing_evidence(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "exited 7 on run 1" in completed.stderr
    assert not output.exists()


def test_benchmark_fails_an_exceeded_median_budget_and_keeps_evidence(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--max-median-ms",
            "0.001",
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "pass",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout.startswith("FAIL label=help")
    result = json.loads(output.read_text())
    assert result["max_median_ms"] == 0.001
    assert result["threshold_passed"] is False


def test_benchmark_rejects_missing_expected_output(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--expect",
            "reefproof-ready",
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "print('wrong output')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "expected stdout marker missing on run 1" in completed.stderr
    assert not output.exists()
