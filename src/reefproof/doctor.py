"""Local-only development health checks."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from reefproof.service.infra_smoke import database_path
from reefproof.service.lifecycle import DaemonLifecycle, DaemonState
from reefproof.service.workbench import EndpointState, observe_workbench
from reefproof.settings import Settings, load_settings
from reefproof.storage import Database

Status = Literal["PASS", "WARN", "FAIL"]


@dataclass(frozen=True)
class Check:
    status: Status
    name: str
    detail: str


def _data_directory_check(settings: Settings) -> Check:
    try:
        directory = settings.ensure_data_directory()
        with tempfile.NamedTemporaryFile(prefix=".reefproof-doctor-", dir=directory):
            pass
    except OSError as error:
        return Check("FAIL", "local data directory", str(error))
    return Check("PASS", "local data directory", f"writable: {directory}")


def _secret_check() -> Check:
    sensitive_markers = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "CREDENTIAL")
    supported_secret_keys = {
        "REEFPROOF_HOME_ASSISTANT_TOKEN",
        "REEFPROOF_BOOTSTRAP_SECRET",
    }
    unsafe = sorted(
        key
        for key in os.environ
        if key.startswith("REEFPROOF_")
        and key not in supported_secret_keys
        and any(marker in key for marker in sensitive_markers)
    )
    if unsafe:
        return Check("FAIL", "safe secret configuration", f"unsupported keys: {', '.join(unsafe)}")
    configured = sorted(key for key in supported_secret_keys if os.environ.get(key))
    detail = (
        f"supported secret configured: {', '.join(configured)}"
        if configured
        else "supported secrets are unset"
    )
    return Check("PASS", "safe secret configuration", detail)


def _storage_check(settings: Settings) -> Check:
    path = database_path(settings.data_directory)
    if not path.is_file():
        return Check("WARN", "SQLite evidence store", f"uninitialized: {path}")
    try:
        database = Database(path)
        integrity = database.integrity_check()
        schema = database.schema_version()
        journal = database.journal_mode()
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        return Check("FAIL", "SQLite evidence store", str(error))
    status: Status = "PASS" if integrity == "ok" and journal.casefold() == "wal" else "FAIL"
    return Check(
        status,
        "SQLite evidence store",
        f"integrity={integrity}; schema={schema}; journal={journal}; path={path}",
    )


def _workbench_process_check(settings: Settings) -> Check:
    lifecycle = DaemonLifecycle(
        settings.data_directory / "reefproof.pid",
        settings.data_directory / "reefproof-daemon.log",
    )
    observation = observe_workbench(settings, lifecycle)
    if observation.daemon.state in {DaemonState.STALE, DaemonState.INVALID}:
        return Check(
            "FAIL",
            "Workbench process",
            observation.daemon.detail or f"daemon PID state={observation.daemon.state.value}",
        )
    if observation.endpoint is EndpointState.FOREIGN:
        return Check("FAIL", "Workbench process", f"foreign listener: {observation.status_url}")
    if observation.managed and observation.endpoint is not EndpointState.REEFPROOF:
        return Check("FAIL", "Workbench process", "managed PID has no valid status endpoint")
    if observation.endpoint is EndpointState.REEFPROOF:
        ownership = "managed" if observation.managed else "unmanaged"
        return Check("PASS", "Workbench process", f"reachable; ownership={ownership}")
    return Check("PASS", "Workbench process", "stopped; no listener")


def run_checks(
    *,
    root: Path | None = None,
    settings: Settings | None = None,
    ledger_path: Path | None = None,
) -> list[Check]:
    project_root = root or Path(__file__).resolve().parents[2]
    checks: list[Check] = []
    checks.append(
        Check(
            "PASS" if sys.version_info[:2] == (3, 13) else "FAIL",
            "Python version",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    required = (
        "AGENTS.md",
        "pyproject.toml",
        "src/reefproof",
        "src/reefproof/configuration",
        "src/reefproof/invariants",
        "src/reefproof/reliability",
        "tests/unit",
        "tests/fixtures/configuration",
    )
    missing = [item for item in required if not (project_root / item).exists()]
    if missing and root is None:
        checks.append(
            Check(
                "PASS",
                "repository structure",
                "installed distribution; source tree is not required at runtime",
            )
        )
    else:
        checks.append(
            Check(
                "FAIL" if missing else "PASS",
                "repository structure",
                (
                    f"missing: {', '.join(missing)}"
                    if missing
                    else (
                        "offline model, invariants, persistence, alerting, "
                        "and service files present"
                    )
                ),
            )
        )
    try:
        loaded = settings or load_settings()
    except ValidationError as error:
        checks.append(Check("FAIL", "configuration loading", str(error).splitlines()[0]))
    else:
        checks.append(Check("PASS", "configuration loading", "typed settings loaded"))
        checks.append(_data_directory_check(loaded))
        checks.append(_storage_check(loaded))
        checks.append(_workbench_process_check(loaded))
    checks.append(
        Check(
            "PASS" if shutil.which("git") else "WARN",
            "Git availability",
            shutil.which("git") or "git not found",
        )
    )
    checks.append(_secret_check())
    transport_found = any(
        importlib.util.find_spec(name) is not None for name in ("pyhydros", "hydros")
    )
    checks.append(
        Check(
            "FAIL" if transport_found else "PASS",
            "HYDROS transport",
            "unexpected transport installed" if transport_found else "not installed",
        )
    )
    del ledger_path
    return checks
