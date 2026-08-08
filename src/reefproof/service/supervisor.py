"""Narrow self-restart handoff to an external production supervisor."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable, Mapping
from threading import Lock, Timer

RESTART_MODE = "supervised-self-terminate"


class SupervisedSelfRestart:
    """Schedule termination of only this process after the API response is returned."""

    def __init__(
        self,
        *,
        terminate: Callable[[], None] = lambda: os.kill(os.getpid(), signal.SIGTERM),
        schedule: Callable[[float, Callable[[], None]], None] | None = None,
        delay_seconds: float = 0.5,
    ) -> None:
        self._terminate = terminate
        self._schedule = schedule or self._schedule_timer
        self._delay_seconds = delay_seconds
        self._requested = False
        self._lock = Lock()

    @staticmethod
    def _schedule_timer(delay: float, callback: Callable[[], None]) -> None:
        timer = Timer(delay, callback)
        timer.daemon = True
        timer.start()

    def request(self) -> str:
        with self._lock:
            if self._requested:
                raise RuntimeError("hosted ReefProof restart is already pending")
            self._requested = True
        self._schedule(self._delay_seconds, self._terminate)
        return "ReefProof self-termination scheduled for the external supervisor"


def configured_restart_service(
    environment: Mapping[str, str],
    *,
    supervisor: SupervisedSelfRestart | None = None,
) -> Callable[[], str] | None:
    mode = environment.get("REEFPROOF_HOSTED_RESTART_MODE")
    if mode is None or mode == "disabled":
        return None
    if mode != RESTART_MODE:
        raise ValueError(f"unsupported hosted restart mode: {mode}")
    runtime_environment = environment.get("REEFPROOF_ENVIRONMENT", "development").casefold()
    if runtime_environment not in {"prod", "production"}:
        raise ValueError("supervised hosted restart requires production environment")
    return (supervisor or SupervisedSelfRestart()).request
