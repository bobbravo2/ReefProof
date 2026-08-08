from __future__ import annotations

import json

from reefproof.service.lifecycle import DaemonState, PidStatus
from reefproof.service.workbench import EndpointState, observe_workbench
from reefproof.settings import Settings


class Lifecycle:
    def __init__(self, state: DaemonState) -> None:
        self.state = state

    def status(self) -> PidStatus:
        return PidStatus(self.state, 42 if self.state is DaemonState.RUNNING else None)


class Response:
    def __init__(self, document: object) -> None:
        self.document = document

    def read(self) -> bytes:
        return json.dumps(self.document).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_observation_keeps_endpoint_identity_and_pid_ownership_distinct(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(
            {
                "version": "0.1.0",
                "operating_mode": "watch",
                "readiness": "unready",
                "monitoring_confidence": "unknown",
            }
        ),
    )

    observation = observe_workbench(Settings(), Lifecycle(DaemonState.STOPPED))  # type: ignore[arg-type]

    assert observation.endpoint is EndpointState.REEFPROOF
    assert observation.managed is False
    assert observation.status_url == "http://127.0.0.1:8787/v1/system/status"
    assert observation.runtime is not None
    assert observation.runtime.operating_mode == "watch"


def test_observation_distinguishes_free_and_foreign_ports(monkeypatch) -> None:
    def refused(*_args, **_kwargs):
        raise OSError

    monkeypatch.setattr("urllib.request.urlopen", refused)
    monkeypatch.setattr("reefproof.service.workbench._port_is_open", lambda *_args: False)
    stopped = observe_workbench(Settings(), Lifecycle(DaemonState.STOPPED))  # type: ignore[arg-type]
    monkeypatch.setattr("reefproof.service.workbench._port_is_open", lambda *_args: True)
    foreign = observe_workbench(Settings(), Lifecycle(DaemonState.RUNNING))  # type: ignore[arg-type]

    assert stopped.endpoint is EndpointState.STOPPED
    assert foreign.endpoint is EndpointState.FOREIGN
    assert foreign.managed is True
