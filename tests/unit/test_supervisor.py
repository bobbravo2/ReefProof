from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from reefproof.service.supervisor import SupervisedSelfRestart, configured_restart_service


def test_supervised_restart_schedules_only_self_termination() -> None:
    scheduled: list[tuple[float, object]] = []
    terminated: list[bool] = []
    supervisor = SupervisedSelfRestart(
        terminate=lambda: terminated.append(True),
        schedule=lambda delay, callback: scheduled.append((delay, callback)),
    )
    restart = configured_restart_service(
        {
            "REEFPROOF_ENVIRONMENT": "production",
            "REEFPROOF_HOSTED_RESTART_MODE": "supervised-self-terminate",
        },
        supervisor=supervisor,
    )
    assert restart is not None
    assert "external supervisor" in restart()
    assert terminated == []
    delay, raw_callback = scheduled.pop()
    assert delay == 0.5
    callback = cast(Callable[[], None], raw_callback)
    callback()
    assert terminated == [True]
    with pytest.raises(RuntimeError, match="already pending"):
        restart()


def test_supervised_restart_is_disabled_by_default_and_rejects_unsafe_configuration() -> None:
    assert configured_restart_service({}) is None
    with pytest.raises(ValueError, match="production"):
        configured_restart_service({"REEFPROOF_HOSTED_RESTART_MODE": "supervised-self-terminate"})
    with pytest.raises(ValueError, match="unsupported"):
        configured_restart_service(
            {
                "REEFPROOF_ENVIRONMENT": "production",
                "REEFPROOF_HOSTED_RESTART_MODE": "shell-command",
            }
        )
