#!/usr/bin/env python3
"""Reject runtime MQTT clients without rejecting offline vendor evidence."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

FORBIDDEN_CLIENT_ROOTS = frozenset({"awsiot", "paho", "pyhydros"})


def import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.partition(".")[0])
    return roots


def violations(source_root: Path) -> list[str]:
    failures: list[str] = []
    for path in sorted(source_root.rglob("*.py")):
        if "mqtt" in path.name.casefold():
            failures.append(f"MQTT-named runtime module: {path}")
        forbidden = sorted(import_roots(path) & FORBIDDEN_CLIENT_ROOTS)
        if forbidden:
            failures.append(f"forbidden transport import in {path}: {', '.join(forbidden)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    source_root = args.root.resolve() / "src" / "reefproof"
    if not source_root.is_dir():
        print(f"FAIL: runtime source directory is missing: {source_root}")
        return 2
    failures = violations(source_root)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: runtime contains no MQTT client or vendor transport import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
