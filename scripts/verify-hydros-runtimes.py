#!/usr/bin/env python3
"""Compare one offline HYDROS evaluation across release runtimes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

FIELDS = (
    "detailed_explanation",
    "evidence",
    "invariant_id",
    "severity",
    "snapshot_hash",
    "state",
    "summary",
)


def load_result(path: Path) -> dict[str, Any]:
    document: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"runtime result must be an object: {path}")
    missing = [field for field in FIELDS if field not in document]
    if missing:
        raise ValueError(f"runtime result is missing field(s): {', '.join(missing)}")
    if not all(isinstance(document[field], str) for field in FIELDS if field != "evidence"):
        raise ValueError(f"runtime result contains a non-string field: {path}")
    evidence = document["evidence"]
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise ValueError(f"runtime result evidence must be a string list: {path}")
    return {field: document[field] for field in FIELDS}


def run(command: list[str], *, cwd: Path, data_directory: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["REEFPROOF_DATA_DIRECTORY"] = str(data_directory)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    document: Any = json.loads(completed.stdout)
    if not isinstance(document, dict):
        raise ValueError("runtime output must be a JSON object")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json") as output:
        json.dump(document, output)
        output.flush()
        return load_result(Path(output.name))


def execute_runtimes(arguments: argparse.Namespace) -> dict[str, dict[str, Any]]:
    source_cli = arguments.source_cli.resolve()
    binary = arguments.binary.resolve()
    hydros_export = arguments.hydros_export.resolve()
    repository = source_cli.parent
    common = [
        "hydros-check",
        "--hydros-export",
        str(hydros_export),
        "--captured-at",
        arguments.captured_at,
        "--expected-temperature-unit",
        arguments.expected_temperature_unit,
        "--format",
        "json",
    ]
    with tempfile.TemporaryDirectory(prefix="reefproof-hydros-parity-") as temporary:
        root = Path(temporary)
        results = {
            "source": run(
                [str(source_cli), *common], cwd=repository, data_directory=root / "source-data"
            ),
            "binary": run([str(binary), *common], cwd=root, data_directory=root / "binary-data"),
        }
        oci_data = root / "oci-data"
        oci_data.mkdir()
        container_export = "/input/hydros.json"
        container_common = common.copy()
        container_common[2] = container_export
        container_command = [
            arguments.container_tool,
            "run",
            "--rm",
            "--read-only",
            "--network=none",
            "--cap-drop=all",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev",
            "--mount",
            f"type=bind,source={oci_data},target=/var/lib/reefproof",
            "--mount",
            f"type=bind,source={hydros_export},target={container_export},readonly",
            arguments.image,
            *container_common,
        ]
        results["oci"] = run(container_command, cwd=repository, data_directory=oci_data)
        return results


def verify(results: dict[str, dict[str, Any]]) -> None:
    source = results["source"]
    if source["invariant_id"] != "RP-UNIT-001":
        raise ValueError("source runtime returned the wrong invariant")
    if source["state"] != "PASS" or source["severity"] != "info":
        raise ValueError("source runtime violates the accepted offline HYDROS result")
    if not str(source["snapshot_hash"]).startswith("sha256:"):
        raise ValueError("source runtime returned an invalid snapshot hash")
    for runtime in ("binary", "oci"):
        for field in FIELDS:
            if results[runtime][field] != source[field]:
                raise ValueError(f"{runtime} runtime differs for {field}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-result", type=Path)
    parser.add_argument("--binary-result", type=Path)
    parser.add_argument("--oci-result", type=Path)
    parser.add_argument("--source-cli", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--container-tool", choices=("docker", "podman"))
    parser.add_argument("--image")
    parser.add_argument("--hydros-export", type=Path)
    parser.add_argument("--captured-at")
    parser.add_argument("--expected-temperature-unit", default="fahrenheit")
    arguments = parser.parse_args()

    result_paths = (arguments.source_result, arguments.binary_result, arguments.oci_result)
    if any(result_paths):
        if not all(result_paths):
            parser.error("source, binary, and OCI result files are required together")
        results = {
            "source": load_result(arguments.source_result),
            "binary": load_result(arguments.binary_result),
            "oci": load_result(arguments.oci_result),
        }
    else:
        required = (
            "source_cli",
            "binary",
            "container_tool",
            "image",
            "hydros_export",
            "captured_at",
        )
        missing = [name.replace("_", "-") for name in required if not getattr(arguments, name)]
        if missing:
            parser.error(f"runtime execution requires: {', '.join(missing)}")
        results = execute_runtimes(arguments)

    verify(results)
    print("PASS: source, binary, and OCI offline HYDROS results match")


if __name__ == "__main__":
    main()
