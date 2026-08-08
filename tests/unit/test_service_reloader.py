from __future__ import annotations

import time
from pathlib import Path
from threading import Event, Thread

from reefproof.service.reloader import wait_for_change, watched_state


def test_watched_state_includes_code_templates_assets_and_config(tmp_path: Path) -> None:
    expected = [
        tmp_path / "app.py",
        tmp_path / "page.html",
        tmp_path / "site.css",
        tmp_path / "site.js",
        tmp_path / "site.ts",
        tmp_path / "settings.yaml",
        tmp_path / "fixture.json",
    ]
    for path in expected:
        path.write_text("initial", encoding="utf-8")
    (tmp_path / "reefproof.sqlite3").write_text("mutable", encoding="utf-8")
    (tmp_path / "notes.md").write_text("docs", encoding="utf-8")

    state = watched_state((tmp_path,))

    assert set(state) == set(expected)


def test_wait_for_change_reports_relevant_change(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("initial", encoding="utf-8")
    stop = Event()

    def change_source() -> None:
        time.sleep(0.03)
        source.write_text("changed and longer", encoding="utf-8")

    thread = Thread(target=change_source)
    thread.start()
    changed = wait_for_change((tmp_path,), stop=stop, poll_interval_seconds=0.01)
    thread.join()

    assert changed == source


def test_wait_for_change_stops_without_change(tmp_path: Path) -> None:
    stop = Event()
    stop.set()

    assert wait_for_change((tmp_path,), stop=stop) is None
