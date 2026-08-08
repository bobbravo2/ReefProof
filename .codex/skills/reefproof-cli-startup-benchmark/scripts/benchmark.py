#!/usr/bin/env python3
"""Measure ReefProof CLI process startup through the repository launcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=positive_int, default=1)
    parser.add_argument("--warmups", type=nonnegative_int, default=0)
    parser.add_argument("--label", default="help")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-median-ms", type=positive_float)
    parser.add_argument("--expect", help="Required UTF-8 stdout marker for every measured run")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def percentile_95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def timed_run(command: list[str], environment: dict[str, str]) -> dict[str, float | int | str]:
    started = time.perf_counter_ns()
    completed = subprocess.run(
        command,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {
        "wall_ms": elapsed_ms,
        "returncode": completed.returncode,
        "stdout_bytes": len(completed.stdout),
        "stderr_bytes": len(completed.stderr),
        "stdout_sha256": digest(completed.stdout),
        "stderr_sha256": digest(completed.stderr),
        "stdout": completed.stdout.decode("utf-8", errors="replace"),
    }


def command_identity(command: list[str]) -> dict[str, str | int | None]:
    executable = command[0]
    resolved = Path(executable) if "/" in executable else None
    if resolved is None:
        located = shutil.which(executable)
        resolved = Path(located) if located else None
    elif not resolved.is_absolute():
        resolved = Path.cwd() / resolved

    if resolved is None or not resolved.is_file():
        return {"path": None, "size_bytes": None, "sha256": None}
    payload = resolved.read_bytes()
    return {
        "path": str(resolved.resolve()),
        "size_bytes": len(payload),
        "sha256": digest(payload),
    }


def git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def default_output(label: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(
        character if character.isalnum() or character in "-_" else "-" for character in label
    )
    return Path(".local/qa-bench/cli-startup") / f"{timestamp}-{safe_label}.json"


def main() -> int:
    args = parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    using_default_command = not command
    if using_default_command:
        command = ["./reefproof", "--help"]
    expected_stdout = args.expect
    if using_default_command and expected_stdout is None:
        expected_stdout = "ReefProof configuration assurance"

    output = args.output or default_output(args.label)
    environment = os.environ.copy()
    environment.update({"COLUMNS": "120", "NO_COLOR": "1", "TERM": "dumb"})
    launcher_mode = environment.get(
        "REEFPROOF_ENV", environment.get("REEFPROOF_ENVIRONMENT", "dev")
    )

    with tempfile.TemporaryDirectory(prefix="reefproof-cli-benchmark-") as state_dir:
        environment["REEFPROOF_DATA_DIRECTORY"] = state_dir
        environment["REEFPROOF_HISTORY_FILE"] = str(Path(state_dir) / "history.log")

        for warmup in range(1, args.warmups + 1):
            result = timed_run(command, environment)
            if result["returncode"] != 0:
                print(
                    f"FAIL warmup command exited {result['returncode']} on warmup {warmup}: "
                    f"{command!r}",
                    file=sys.stderr,
                )
                return 2
            if expected_stdout is not None and expected_stdout not in str(result["stdout"]):
                print(
                    f"FAIL expected stdout marker missing on warmup {warmup}: {expected_stdout!r}",
                    file=sys.stderr,
                )
                return 2

        measurements: list[dict[str, float | int | str]] = []
        for iteration in range(1, args.runs + 1):
            result = timed_run(command, environment)
            if result["returncode"] != 0:
                print(
                    f"FAIL measured command exited {result['returncode']} on run {iteration}: "
                    f"{command!r}",
                    file=sys.stderr,
                )
                return 2
            if expected_stdout is not None and expected_stdout not in str(result["stdout"]):
                print(
                    f"FAIL expected stdout marker missing on run {iteration}: {expected_stdout!r}",
                    file=sys.stderr,
                )
                return 2
            result.pop("stdout")
            result["iteration"] = iteration
            measurements.append(result)

    samples = [float(measurement["wall_ms"]) for measurement in measurements]
    output_stable = (
        len(
            {
                (measurement["stdout_sha256"], measurement["stderr_sha256"])
                for measurement in measurements
            }
        )
        == 1
    )

    median_ms = statistics.median(samples)
    threshold_passed = args.max_median_ms is None or median_ms <= args.max_median_ms
    result = {
        "schema_version": 2,
        "recorded_at": datetime.now(UTC).isoformat(),
        "label": args.label,
        "command": command,
        "command_identity": command_identity(command),
        "cwd": str(Path.cwd()),
        "git_commit": git_commit(),
        "launcher_mode": launcher_mode,
        "runs": args.runs,
        "warmups": args.warmups,
        "expected_stdout": expected_stdout,
        "normalized_environment": {"COLUMNS": "120", "NO_COLOR": "1", "TERM": "dumb"},
        "measurements": measurements,
        "samples_ms": samples,
        "output_stable": output_stable,
        "summary_ms": {
            "min": min(samples),
            "median": median_ms,
            "mean": statistics.fmean(samples),
            "p95": percentile_95(samples),
            "max": max(samples),
            "population_stdev": statistics.pstdev(samples),
        },
        "max_median_ms": args.max_median_ms,
        "threshold_passed": threshold_passed,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = "PASS" if threshold_passed else "FAIL"
    summary = result["summary_ms"]
    print(
        f"{status} label={args.label} runs={args.runs} warmups={args.warmups} "
        f"median_ms={summary['median']:.3f} min_ms={summary['min']:.3f} "
        f"max_ms={summary['max']:.3f} output={output}"
    )
    return 0 if threshold_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
