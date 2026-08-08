"""Portable PID-file supervision for the local ReefProof daemon."""

from __future__ import annotations

import errno
import os
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final


class DaemonState(StrEnum):
    """The observable state of a PID file and its recorded process."""

    STOPPED = "stopped"
    RUNNING = "running"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class PidStatus:
    """A bounded, read-only observation of one daemon PID file."""

    state: DaemonState
    pid: int | None = None
    detail: str | None = None


class LifecycleError(RuntimeError):
    """A requested daemon lifecycle transition could not be completed."""


class PidWatcher:
    """Observe a PID file and wait for its process to exit."""

    def __init__(self, pid_file: Path) -> None:
        self.pid_file = pid_file

    def status(self) -> PidStatus:
        """Return whether the PID file is absent, active, stale, or malformed."""

        if not self.pid_file.exists():
            return PidStatus(DaemonState.STOPPED)
        try:
            raw_pid = self.pid_file.read_text(encoding="utf-8").strip()
            pid = int(raw_pid)
        except (OSError, ValueError):
            return PidStatus(
                DaemonState.INVALID,
                detail=f"PID file is not a valid integer: {self.pid_file}",
            )
        if pid <= 0:
            return PidStatus(
                DaemonState.INVALID,
                pid=pid,
                detail=f"PID must be positive: {self.pid_file}",
            )
        if process_is_alive(pid):
            return PidStatus(DaemonState.RUNNING, pid=pid)
        return PidStatus(DaemonState.STALE, pid=pid)

    def remove_stale(self) -> None:
        """Remove only a PID file that no longer identifies a live process."""

        status = self.status()
        if status.state is DaemonState.STALE:
            try:
                self.pid_file.unlink()
            except FileNotFoundError:
                return
        elif status.state is DaemonState.INVALID:
            raise LifecycleError(status.detail or "invalid PID file")

    def wait_until_stopped(
        self,
        *,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.1,
    ) -> PidStatus:
        """Wait for the recorded process to stop, returning its final status."""

        deadline = time.monotonic() + timeout_seconds
        while True:
            status = self.status()
            if status.state is not DaemonState.RUNNING:
                return status
            if time.monotonic() >= deadline:
                return status
            time.sleep(poll_interval_seconds)

    def terminate(self, *, timeout_seconds: float = 10.0) -> PidStatus:
        """Request graceful termination of the recorded process and wait."""

        status = self.status()
        if status.state is DaemonState.STOPPED:
            return status
        if status.state is DaemonState.STALE:
            self.remove_stale()
            return PidStatus(DaemonState.STOPPED)
        if status.state is DaemonState.INVALID or status.pid is None:
            raise LifecycleError(status.detail or "invalid PID file")
        try:
            os.kill(status.pid, signal.SIGTERM)
        except ProcessLookupError:
            self.remove_stale()
            return PidStatus(DaemonState.STOPPED)
        final = self.wait_until_stopped(timeout_seconds=timeout_seconds)
        if final.state is DaemonState.RUNNING:
            raise LifecycleError(
                f"daemon PID {status.pid} did not stop within {timeout_seconds:g} seconds"
            )
        if final.state is DaemonState.STALE:
            self.remove_stale()
            return PidStatus(DaemonState.STOPPED)
        return final


def process_is_alive(pid: int) -> bool:
    """Check process existence without inspecting or changing the process."""

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        if error.errno == errno.ESRCH:
            return False
        if error.errno == errno.EPERM:
            return True
        raise
    return True


DEFAULT_STOP_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(frozen=True, slots=True)
class DaemonLifecycle:
    """Start, stop, and inspect one local foreground ``serve`` child."""

    pid_file: Path
    log_file: Path

    @property
    def watcher(self) -> PidWatcher:
        return PidWatcher(self.pid_file)

    def status(self) -> PidStatus:
        """Return the current process observation."""

        return self.watcher.status()

    def start(self, command: Sequence[str]) -> PidStatus:
        """Start one detached child, recording its PID only after spawn succeeds."""

        watcher = self.watcher
        current = watcher.status()
        if current.state is DaemonState.RUNNING:
            raise LifecycleError(f"daemon is already running with PID {current.pid}")
        watcher.remove_stale()
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.log_file.open("a", encoding="utf-8") as log_stream:
                child = subprocess.Popen(
                    list(command),
                    stdin=subprocess.DEVNULL,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as error:
            raise LifecycleError(f"could not start daemon: {error}") from error
        try:
            self.pid_file.write_text(f"{child.pid}\n", encoding="utf-8")
        except OSError as error:
            child.terminate()
            raise LifecycleError(f"could not write PID file {self.pid_file}: {error}") from error
        return PidStatus(DaemonState.RUNNING, pid=child.pid)

    def stop(self, *, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> PidStatus:
        """Gracefully stop the recorded child and remove a stale PID file."""

        return self.watcher.terminate(timeout_seconds=timeout_seconds)
