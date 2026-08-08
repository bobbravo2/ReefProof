"""Bounded polling restart watcher for local development."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from threading import Event

WATCHED_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".py", ".ts", ".yaml", ".yml"})


def default_reload_roots() -> tuple[Path, ...]:
    """Return source and authored configuration roots, excluding mutable data."""

    repository_root = Path(__file__).resolve().parents[3]
    roots = (repository_root / "src", repository_root / "config")
    return tuple(path for path in roots if path.is_dir())


def watched_state(roots: Iterable[Path]) -> dict[Path, int]:
    """Capture modification times for reload-relevant regular files."""

    state: dict[Path, int] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in WATCHED_SUFFIXES:
                try:
                    state[path] = path.stat().st_mtime_ns
                except FileNotFoundError:
                    continue
    return state


def wait_for_change(
    roots: tuple[Path, ...],
    *,
    stop: Event,
    poll_interval_seconds: float = 0.25,
) -> Path | None:
    """Return one changed path, or None when the server stops normally."""

    previous = watched_state(roots)
    while not stop.wait(poll_interval_seconds):
        current = watched_state(roots)
        changed = sorted(
            path
            for path in previous.keys() | current.keys()
            if previous.get(path) != current.get(path)
        )
        if changed:
            return changed[0]
        previous = current
    return None
