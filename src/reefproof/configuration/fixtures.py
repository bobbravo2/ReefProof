"""Strict fixture loading and deterministic canonical snapshot export."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from reefproof.configuration.models import ConfigurationFixture, ConfigurationSnapshot
from reefproof.configuration.normalize import normalize_fixture


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_fixture(path: Path) -> ConfigurationFixture:
    """Load one strict repository-authored JSON fixture."""

    with path.open(encoding="utf-8") as stream:
        document = json.load(stream, object_pairs_hook=_unique_object)
    return ConfigurationFixture.model_validate(document)


def snapshot_fixture(fixture: ConfigurationFixture) -> ConfigurationSnapshot:
    """Normalize one authored fixture into canonical snapshot evidence."""

    return normalize_fixture(fixture)


def render_snapshot(snapshot: ConfigurationSnapshot) -> str:
    """Render stable, human-readable JSON with a trailing newline."""

    document = snapshot.model_dump(mode="json")
    return f"{json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)}\n"


def write_snapshot(snapshot: ConfigurationSnapshot, output: Path) -> None:
    """Atomically write a canonical snapshot to an explicit local path."""

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(render_snapshot(snapshot))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
