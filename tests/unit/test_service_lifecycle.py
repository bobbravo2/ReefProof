from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest

from reefproof.service.lifecycle import (
    DaemonLifecycle,
    DaemonState,
    LifecycleError,
    PidWatcher,
    process_is_alive,
)


def test_pid_watcher_reports_stopped_running_stale_and_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "reefproof.pid"
    watcher = PidWatcher(pid_file)

    assert watcher.status().state is DaemonState.STOPPED

    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert watcher.status().state is DaemonState.RUNNING

    pid_file.write_text("999999999\n", encoding="utf-8")
    monkeypatch.setattr("reefproof.service.lifecycle.process_is_alive", lambda pid: False)
    assert watcher.status().state is DaemonState.STALE
    watcher.remove_stale()
    assert not pid_file.exists()

    pid_file.write_text("not-a-pid\n", encoding="utf-8")
    assert watcher.status().state is DaemonState.INVALID
    with pytest.raises(LifecycleError, match="valid integer"):
        watcher.remove_stale()


def test_process_is_alive_distinguishes_missing_and_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(pid: int, signal_number: int) -> None:
        raise ProcessLookupError(pid)

    monkeypatch.setattr("reefproof.service.lifecycle.os.kill", missing)
    assert process_is_alive(123) is False

    def denied(pid: int, signal_number: int) -> None:
        raise PermissionError(pid)

    monkeypatch.setattr("reefproof.service.lifecycle.os.kill", denied)
    assert process_is_alive(123) is True


def test_lifecycle_starts_child_records_pid_and_uses_detached_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChild:
        pid = 4321

        def terminate(self) -> None:
            raise AssertionError("child should not be terminated")

    calls: list[dict[str, object]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeChild:
        calls.append({"command": command, **kwargs})
        return FakeChild()

    monkeypatch.setattr("reefproof.service.lifecycle.subprocess.Popen", fake_popen)
    monkeypatch.setattr("reefproof.service.lifecycle.process_is_alive", lambda pid: pid == 4321)
    lifecycle = DaemonLifecycle(
        pid_file=tmp_path / "run" / "reefproof.pid",
        log_file=tmp_path / "logs" / "reefproof.log",
    )

    status = lifecycle.start(("reefproof", "serve", "--no-open", "--no-reload"))

    assert status == lifecycle.status()
    assert status.state is DaemonState.RUNNING
    assert status.pid == 4321
    assert lifecycle.pid_file.read_text(encoding="utf-8") == "4321\n"
    assert lifecycle.log_file.exists()
    assert calls[0]["command"] == ["reefproof", "serve", "--no-open", "--no-reload"]
    assert calls[0]["start_new_session"] is True
    assert calls[0]["stdin"] is subprocess.DEVNULL
    assert calls[0]["stderr"] is subprocess.STDOUT


def test_lifecycle_rejects_running_daemon_without_spawning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "reefproof.pid"
    pid_file.write_text("123\n", encoding="utf-8")
    monkeypatch.setattr("reefproof.service.lifecycle.process_is_alive", lambda pid: True)
    monkeypatch.setattr(
        "reefproof.service.lifecycle.subprocess.Popen",
        lambda *args, **kwargs: pytest.fail("unexpected second daemon"),
    )

    with pytest.raises(LifecycleError, match="already running"):
        DaemonLifecycle(pid_file=pid_file, log_file=tmp_path / "reefproof.log").start(
            ("reefproof",)
        )


def test_lifecycle_stop_sends_sigterm_and_cleans_pid_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid_file = tmp_path / "reefproof.pid"
    pid_file.write_text("123\n", encoding="utf-8")
    alive = True
    signals: list[tuple[int, int]] = []

    def fake_alive(pid: int) -> bool:
        return alive

    def fake_kill(pid: int, signal_number: int) -> None:
        nonlocal alive
        signals.append((pid, signal_number))
        alive = False

    monkeypatch.setattr("reefproof.service.lifecycle.process_is_alive", fake_alive)
    monkeypatch.setattr("reefproof.service.lifecycle.os.kill", fake_kill)
    monkeypatch.setattr("reefproof.service.lifecycle.time.sleep", lambda seconds: None)

    status = DaemonLifecycle(pid_file=pid_file, log_file=tmp_path / "reefproof.log").stop(
        timeout_seconds=0.1
    )

    assert status.state is DaemonState.STOPPED
    assert signals == [(123, signal.SIGTERM)]
    assert not pid_file.exists()
