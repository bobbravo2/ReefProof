"""Construct the local service from explicit application dependencies."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import TextIO
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI

from reefproof.alerting import (
    AlertCoordinator,
    AlertPolicy,
    ConsoleAlertAdapter,
    HomeAssistantAlertAdapter,
)
from reefproof.alerting.protocol import AlertAdapter
from reefproof.api import create_app
from reefproof.api.operations import LocalHostedOperations
from reefproof.authored_sources import (
    GoogleServiceAccountCredentialProvider,
    GoogleSheetsSource,
)
from reefproof.project_state import Project
from reefproof.project_store import ProjectStore
from reefproof.service.pipeline import FixtureEvaluationPipeline
from reefproof.service.reloader import default_reload_roots, wait_for_change
from reefproof.service.state import RuntimeStateStore
from reefproof.service.supervisor import configured_restart_service
from reefproof.settings import (
    ConsoleAdapterSettings,
    HomeAssistantAdapterSettings,
    Settings,
)
from reefproof.storage import Database, RetentionReport

ACCESS_LOG_FORMAT = '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
SERVER_LOG_FORMAT = "%(levelprefix)s %(message)s"


@dataclass(frozen=True, slots=True)
class ServiceRuntime:
    settings: Settings
    database: Database
    retention_report: RetentionReport | None
    state: RuntimeStateStore
    alert_coordinators: tuple[AlertCoordinator, ...]
    fixture_pipeline: FixtureEvaluationPipeline
    app: FastAPI


def build_runtime(
    settings: Settings,
    *,
    started_at: datetime | None = None,
    retention_now: datetime | None = None,
    console_stream: TextIO | None = None,
) -> ServiceRuntime:
    """Build one local runtime without starting a network listener."""

    database = Database(settings.data_directory / "reefproof.sqlite3")
    database.migrate()
    retention_report = None
    retention_days = settings.storage.evaluation_detail_retention_days
    if retention_days is not None:
        reference_time = retention_now or datetime.now(UTC)
        retention_report = database.prune_evaluation_details(
            before=reference_time - timedelta(days=retention_days)
        )
    runtime_started_at = started_at or datetime.now(UTC)
    state = RuntimeStateStore.from_settings(
        settings,
        started_at=runtime_started_at,
    )
    project_store = ProjectStore(database.path)
    projects = project_store.list_projects()
    configured_project_id = settings.project.project_id
    if projects:
        if len(projects) == 1:
            active_project = projects[0]
        else:
            matching_projects = tuple(
                project for project in projects if project.project_id == configured_project_id
            )
            if len(matching_projects) != 1:
                known_project_ids = ", ".join(project.project_id for project in projects)
                raise ValueError(
                    "v0.1 runtime requires one configured durable project; "
                    f"configured={configured_project_id}, known={known_project_ids}"
                )
            active_project = matching_projects[0]
    else:
        active_project = project_store.ensure_project(
            Project(
                project_id=settings.project.project_id,
                name=settings.project.display_name,
                acceptance_authority_principal_id=(
                    settings.project.acceptance_authority_principal_id
                ),
                created_at=runtime_started_at,
            )
        )
    alert_policy = AlertPolicy(
        repeat_critical_after_seconds=(settings.alerts.repeat_critical_after_seconds),
        alert_critical_unknown=(settings.evaluation.critical_unknown_policy == "alert"),
        send_recovery=settings.alerts.send_recovery,
    )
    alert_coordinators = tuple(
        AlertCoordinator(
            database=database,
            policy=alert_policy,
            adapter=adapter,
            reefproof_base_url=_local_base_url(settings),
        )
        for adapter in _build_adapters(settings, console_stream=console_stream)
    )
    pipeline = FixtureEvaluationPipeline(
        database=database,
        alert_coordinators=alert_coordinators,
        runtime_state=state,
    )
    bootstrap_secret = _resolve_bootstrap_secret()
    print(
        "ReefProof bootstrap shared secret "
        "(use once to establish a session before authenticator app enrollment): "
        f"{bootstrap_secret}",
        flush=True,
    )
    google_source_settings = settings.authored_sources.google_sheets
    authored_source = (
        GoogleSheetsSource(
            spreadsheet_id=google_source_settings.spreadsheet_id,
            source_alias=google_source_settings.source_alias,
            credentials=GoogleServiceAccountCredentialProvider(
                google_source_settings.credential_file
            ),
        )
        if google_source_settings.enabled
        and google_source_settings.spreadsheet_id is not None
        and google_source_settings.credential_file is not None
        else None
    )
    app = create_app(
        runtime_state=state.snapshot,
        database=database,
        bootstrap_secret=bootstrap_secret,
        acceptance_principal_id=settings.project.acceptance_authority_principal_id,
        acceptance_principal_display_name=settings.project.acceptance_authority_display_name,
        project_store=project_store,
        active_project_id=active_project.project_id,
        active_project_name=active_project.name,
        authored_source=authored_source,
        authored_source_freshness_seconds=google_source_settings.freshness_seconds,
        session_https_only=settings.api.session_https_only,
        hosted_operations=LocalHostedOperations(
            database=database,
            data_directory=settings.data_directory,
            backup_directory=settings.storage.backup_directory,
            now=lambda: datetime.now(ZoneInfo(settings.timezone)),
            restart_service=configured_restart_service(os.environ),
        ),
    )
    return ServiceRuntime(
        settings=settings,
        database=database,
        retention_report=retention_report,
        state=state,
        alert_coordinators=alert_coordinators,
        fixture_pipeline=pipeline,
        app=app,
    )


def _build_workbench_assets() -> None:
    """Rebuild the generated workbench browser bundle when development reload is enabled."""

    repository_root = Path(__file__).resolve().parents[3]
    package_json = repository_root / "package.json"
    if not package_json.exists() or shutil.which("npm") is None:
        return

    if not _workbench_assets_require_rebuild(repository_root):
        return

    completed = subprocess.run(
        ["npm", "run", "build"],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print("Frontend build failed; continuing with existing assets:", flush=True)
        print(completed.stdout, flush=True)


def _workbench_assets_require_rebuild(repository_root: Path) -> bool:
    """Return true when generated browser assets are missing or stale."""

    workbench_ts = repository_root / "src/reefproof/api/web/typescript/workbench.ts"
    workbench_js = repository_root / "src/reefproof/api/web/static/workbench.js"
    tsconfig = repository_root / "tsconfig.json"
    package_json = repository_root / "package.json"

    if not workbench_js.exists():
        return True
    if not workbench_ts.exists():
        return False

    output_mtime = workbench_js.stat().st_mtime
    for candidate in (workbench_ts, tsconfig, package_json):
        if candidate.exists() and candidate.stat().st_mtime > output_mtime:
            return True
    return False


def _resolve_bootstrap_secret() -> str:
    configured = os.environ.get("REEFPROOF_BOOTSTRAP_SECRET")
    if (
        configured is not None
        and configured.strip() != ""
        and configured.strip() != "generated-per-start"
    ):
        return configured.strip()
    return secrets.token_urlsafe(24)


def run_api(
    runtime: ServiceRuntime,
    *,
    on_started: Callable[[], None] | None = None,
    reload: bool = False,
    runtime_factory: Callable[[], ServiceRuntime] | None = None,
) -> None:
    """Run the already-constructed local API until graceful shutdown."""

    if reload and runtime_factory is None:
        raise ValueError("reload requires a runtime factory")

    current_runtime = runtime
    notify_started = on_started
    while True:
        # Always attempt a startup rebuild so local first-run serve commands pick up
        # generated browser bundle changes from current TypeScript sources.
        _build_workbench_assets()
        server = uvicorn.Server(
            uvicorn.Config(
                current_runtime.app,
                host=current_runtime.settings.api.bind,
                port=current_runtime.settings.api.port,
                log_config=_stdout_log_config(
                    level=current_runtime.settings.log_level,
                    use_colors=_stdout_supports_color(),
                ),
                access_log=True,
            )
        )
        if notify_started is not None:
            Thread(
                target=_notify_when_started,
                args=(server, notify_started),
                daemon=True,
                name="reefproof-server-started",
            ).start()

        changed_path: list[Path] = []
        watcher_stop = Event()
        if reload:
            Thread(
                target=_request_restart_on_change,
                args=(server, default_reload_roots(), watcher_stop, changed_path),
                daemon=True,
                name="reefproof-development-reloader",
            ).start()

        server.run()
        watcher_stop.set()
        if not changed_path:
            return

        print(f"Restarting after change: {changed_path[0]}", flush=True)
        assert runtime_factory is not None
        current_runtime = runtime_factory()
        notify_started = None


def _request_restart_on_change(
    server: uvicorn.Server,
    roots: tuple[Path, ...],
    stop: Event,
    changed_path: list[Path],
) -> None:
    path = wait_for_change(roots, stop=stop)
    if path is not None:
        changed_path.append(path)
        server.should_exit = True


def _notify_when_started(
    server: uvicorn.Server,
    callback: Callable[[], None],
) -> None:
    """Invoke a local UI callback only after Uvicorn accepts connections."""

    deadline = time.monotonic() + 30
    while not server.started and not server.should_exit and time.monotonic() < deadline:
        time.sleep(0.05)
    if server.started:
        callback()


def _stdout_supports_color() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


def _stdout_log_config(*, level: str, use_colors: bool) -> dict[str, object]:
    """Route server and access logs to one operator-visible stdout stream."""

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "server": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": SERVER_LOG_FORMAT,
                "use_colors": use_colors,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": ACCESS_LOG_FORMAT,
                "use_colors": use_colors,
            },
        },
        "handlers": {
            "server": {
                "class": "logging.StreamHandler",
                "formatter": "server",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["server"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["server"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"],
                "level": level,
                "propagate": False,
            },
        },
    }


def _build_adapters(
    settings: Settings,
    *,
    console_stream: TextIO | None,
) -> tuple[AlertAdapter, ...]:
    adapters: list[AlertAdapter] = []
    for adapter in settings.alerts.adapters:
        if isinstance(adapter, ConsoleAdapterSettings):
            adapters.append(ConsoleAlertAdapter(console_stream))
        elif isinstance(adapter, HomeAssistantAdapterSettings):
            endpoint = os.environ.get("REEFPROOF_HOME_ASSISTANT_ENDPOINT")
            bearer_token = os.environ.get("REEFPROOF_HOME_ASSISTANT_TOKEN")
            if not endpoint or not bearer_token:
                raise ValueError(
                    "home_assistant alerts require REEFPROOF_HOME_ASSISTANT_ENDPOINT "
                    "and REEFPROOF_HOME_ASSISTANT_TOKEN"
                )
            adapters.append(
                HomeAssistantAlertAdapter(
                    endpoint=endpoint,
                    bearer_token=bearer_token,
                )
            )
        else:
            raise TypeError(f"unsupported alert adapter settings: {type(adapter).__name__}")
    return tuple(adapters)


def _local_base_url(settings: Settings) -> str:
    host = settings.api.bind
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{settings.api.port}"
