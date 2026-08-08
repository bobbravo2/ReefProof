#!/usr/bin/env python3
"""Export browser-consumable ReefProof API contracts for TypeScript generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Never

from reefproof.api import create_app
from reefproof.service import RuntimeState
from reefproof.storage import Database


def _unreachable_runtime_state() -> RuntimeState:
    raise RuntimeError("contract export must not evaluate runtime state")


def export_schema(output: Path) -> None:
    app = create_app(
        runtime_state=_unreachable_runtime_state,
        database=Database(Path(".local/contract-export-unused.sqlite3")),
    )
    document = app.openapi()
    document["paths"] = {
        path: value
        for path, value in document["paths"].items()
        if path.startswith("/v1/workbench")
        or path.startswith("/v1/projects")
        or path.startswith("/v1/database")
        or path.startswith("/v1/operations")
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> Never:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".local/workbench-openapi.json"),
    )
    arguments = parser.parse_args()
    export_schema(arguments.output)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
