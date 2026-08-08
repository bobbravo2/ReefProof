"""Read-only observation of the configured local ReefProof Workbench."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from reefproof.service.lifecycle import DaemonLifecycle, DaemonState, PidStatus
from reefproof.settings import Settings


class EndpointState(StrEnum):
    REEFPROOF = "reefproof"
    STOPPED = "stopped"
    FOREIGN = "foreign"


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    version: str
    operating_mode: str
    readiness: str
    monitoring_confidence: str


@dataclass(frozen=True, slots=True)
class WorkbenchObservation:
    endpoint: EndpointState
    daemon: PidStatus
    workbench_url: str
    status_url: str
    runtime: RuntimeStatus | None = None

    @property
    def managed(self) -> bool:
        return self.daemon.state is DaemonState.RUNNING


def _hosts(settings: Settings) -> tuple[str, str]:
    configured = settings.api.bind
    probe = "127.0.0.1" if configured in {"0.0.0.0", "::"} else configured
    browser = f"[{configured}]" if ":" in configured else configured
    return probe, browser


def _runtime_status(document: Any) -> RuntimeStatus:
    if not isinstance(document, dict):
        raise ValueError("status response is not an object")

    def required_string(name: str) -> str:
        value = document.get(name)
        if not isinstance(value, str):
            raise ValueError("status response is missing required string fields")
        return value

    return RuntimeStatus(
        version=required_string("version"),
        operating_mode=required_string("operating_mode"),
        readiness=required_string("readiness"),
        monitoring_confidence=required_string("monitoring_confidence"),
    )


def _port_is_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def observe_workbench(
    settings: Settings,
    lifecycle: DaemonLifecycle,
    *,
    timeout: float = 1.5,
) -> WorkbenchObservation:
    """Observe endpoint identity and PID ownership without changing either."""

    probe_host, browser_host = _hosts(settings)
    workbench_url = f"http://{browser_host}:{settings.api.port}/workbench"
    status_url = f"http://{probe_host}:{settings.api.port}/v1/system/status"
    daemon = lifecycle.status()
    try:
        with urllib.request.urlopen(status_url, timeout=timeout) as response:
            raw_document = response.read()
    except (OSError, urllib.error.URLError):
        endpoint = (
            EndpointState.FOREIGN
            if _port_is_open(probe_host, settings.api.port, timeout)
            else EndpointState.STOPPED
        )
        return WorkbenchObservation(endpoint, daemon, workbench_url, status_url)
    try:
        runtime = _runtime_status(json.loads(raw_document))
    except (json.JSONDecodeError, TypeError, ValueError):
        return WorkbenchObservation(
            EndpointState.FOREIGN,
            daemon,
            workbench_url,
            status_url,
        )
    return WorkbenchObservation(
        EndpointState.REEFPROOF,
        daemon,
        workbench_url,
        status_url,
        runtime,
    )
