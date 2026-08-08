#!/usr/bin/env python3
"""Shared path handling for ReefProof distribution scripts."""

from __future__ import annotations

from pathlib import Path


def resolve_under_root(root: Path, value: Path, *, label: str) -> tuple[Path, Path]:
    """Resolve *value* beneath *root* and return (absolute, relative)."""
    resolved_root = root.resolve()
    candidate = value if value.is_absolute() else resolved_root / value
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes root {resolved_root}: {value}") from exc
    if relative == Path("."):
        raise ValueError(f"{label} must name a file beneath root: {value}")
    return resolved, relative


def resolve_output(value: Path) -> Path:
    """Resolve an output path relative to the current working directory."""
    return value if value.is_absolute() else value.resolve()
