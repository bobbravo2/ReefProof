#!/usr/bin/env python3
"""Prepare the tracked, allowlisted build staging tree for ReefProof packaging."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ALLOWLIST = (
    Path(".dockerignore"),
    Path("Dockerfile"),
    Path("README.md"),
    Path("pyproject.toml"),
    Path("src"),
    Path("scripts/write-build-identity.py"),
    Path("uv.lock"),
)

REQUIRED_RELEASE_FILES = (Path("src/reefproof/api/web/static/workbench.js"),)


def tracked_files(repo_root: Path) -> list[Path]:
    command = ["git", "-C", str(repo_root), "ls-files", "-z", "--", *map(str, ALLOWLIST)]
    result = subprocess.run(command, check=True, capture_output=True)
    paths = [Path(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw]

    for required in ALLOWLIST:
        present = (
            required in paths
            if required.suffix or required.name.startswith(".")
            else any(path == required or required in path.parents for path in paths)
        )
        if not present:
            raise FileNotFoundError(f"missing tracked build input: {required}")

    for required in REQUIRED_RELEASE_FILES:
        if required not in paths:
            raise FileNotFoundError(f"missing tracked release input: {required}")

    return sorted(paths, key=lambda path: path.as_posix())


def validate_output(repo_root: Path, output: Path) -> None:
    if output == repo_root:
        raise ValueError("build staging output must not be the repository root")
    try:
        repo_root.relative_to(output)
    except ValueError:
        return
    raise ValueError("build staging output must not contain the repository root")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path(".build/stage"))
    arguments = parser.parse_args()

    repo_root = arguments.repo.resolve()
    output = arguments.output if arguments.output.is_absolute() else repo_root / arguments.output
    output = output.resolve()
    validate_output(repo_root, output)

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    for relative_path in tracked_files(repo_root):
        source = repo_root / relative_path
        if source.is_symlink():
            raise ValueError(f"tracked symlink is not allowed in build staging: {relative_path}")
        if not source.is_file():
            raise FileNotFoundError(f"missing tracked build input: {relative_path}")
        destination = output / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    print(f"PASS: staged tracked build inputs at {output}")


if __name__ == "__main__":
    main()
