from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from reefproof.project_state import Project
from reefproof.project_store import ProjectStore
from reefproof.service.runtime import (
    ACCESS_LOG_FORMAT,
    SERVER_LOG_FORMAT,
    _stdout_log_config,
    build_runtime,
)
from reefproof.settings import (
    AlertsSettings,
    ConsoleAdapterSettings,
    HomeAssistantAdapterSettings,
    ReefProofSettings,
    Settings,
    StorageSettings,
)
from reefproof.storage import DATABASE_SCHEMA_VERSION, Database

NOW = datetime.fromisoformat("2026-07-26T00:00:00-04:00")
UNSAFE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _authenticated_get(app, path: str, token: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            session = await client.post(
                "/v1/workbench/operator-sessions",
                json={"bootstrap_secret": token},
            )
            assert session.status_code == 201
            return await client.get(path)

    return asyncio.run(request())


def test_runtime_factory_wires_database_pipeline_state_and_api(tmp_path: Path) -> None:
    settings = Settings(reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture"))
    stream = io.StringIO()

    runtime = build_runtime(settings, started_at=NOW, console_stream=stream)

    assert runtime.database.schema_version() == DATABASE_SCHEMA_VERSION
    assert ProjectStore(runtime.database.path).list_projects()[0].project_id == (
        "primary-reef-system"
    )
    assert _get(runtime.app, "/v1/system/health/live").status_code == 200
    assert _get(runtime.app, "/v1/system/health/ready").status_code == 503

    asyncio.run(
        runtime.fixture_pipeline.run(
            UNSAFE,
            evaluation_timestamp=NOW,
            evaluation_run_id="92345678-abcd-4234-8234-123456789abc",
        )
    )

    status = _get(runtime.app, "/v1/system/status").json()
    assert status["configuration_hash"]
    assert status["last_evaluation_at"]
    assert status["alert_delivery_state"] == "healthy"
    assert "RP-CIRC-001" in stream.getvalue()
    assert runtime.retention_report is None


def test_runtime_adopts_one_existing_project_without_relabeling(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    store = ProjectStore(database.path)
    store.record_project(
        Project(
            project_id="legacy-reef-system",
            name="Historic reef system",
            acceptance_authority_principal_id="historic-authority",
            created_at=NOW,
        )
    )
    monkeypatch.setenv("REEFPROOF_BOOTSTRAP_SECRET", "configured-factor")

    runtime = build_runtime(
        Settings(reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture")),
        started_at=NOW,
        console_stream=io.StringIO(),
    )

    projects = ProjectStore(database.path).list_projects()
    assert len(projects) == 1
    assert projects[0].project_id == "legacy-reef-system"
    response = _authenticated_get(
        runtime.app,
        "/v1/projects/legacy-reef-system/state",
        "configured-factor",
    )
    assert response.status_code == 200
    assert response.json()["project_id"] == "legacy-reef-system"


def test_runtime_selects_configured_project_when_multiple_durable_projects_exist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    store = ProjectStore(database.path)
    store.record_project(
        Project(
            project_id="legacy-reef-system",
            name="Historic reef system",
            acceptance_authority_principal_id="historic-authority",
            created_at=NOW,
        )
    )
    store.record_project(
        Project(
            project_id="primary-reef-system",
            name="Primary Reef System",
            acceptance_authority_principal_id="local-acceptance-authority",
            created_at=NOW,
        )
    )
    monkeypatch.setenv("REEFPROOF_BOOTSTRAP_SECRET", "configured-factor")

    runtime = build_runtime(
        Settings(reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture")),
        started_at=NOW,
        console_stream=io.StringIO(),
    )

    projects = ProjectStore(database.path).list_projects()
    assert len(projects) == 2
    assert {project.project_id for project in projects} == {
        "legacy-reef-system",
        "primary-reef-system",
    }
    response = _authenticated_get(
        runtime.app,
        "/v1/projects/primary-reef-system/state",
        "configured-factor",
    )
    assert response.status_code == 200
    assert response.json()["project_id"] == "primary-reef-system"


def test_runtime_rejects_multiple_projects_without_configured_identity(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    store = ProjectStore(database.path)
    store.record_project(
        Project(
            project_id="legacy-reef-system-a",
            name="Historic reef system A",
            acceptance_authority_principal_id="historic-authority-a",
            created_at=NOW,
        )
    )
    store.record_project(
        Project(
            project_id="legacy-reef-system-b",
            name="Historic reef system B",
            acceptance_authority_principal_id="historic-authority-b",
            created_at=NOW,
        )
    )

    with pytest.raises(ValueError, match="configured durable project"):
        build_runtime(
            Settings(reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture")),
            started_at=NOW,
            console_stream=io.StringIO(),
        )


def test_runtime_applies_only_explicit_retention(tmp_path: Path) -> None:
    settings = Settings(
        reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture"),
        storage=StorageSettings(evaluation_detail_retention_days=30),
    )

    runtime = build_runtime(
        settings,
        started_at=NOW,
        retention_now=NOW,
        console_stream=io.StringIO(),
    )

    assert runtime.retention_report is not None
    assert runtime.retention_report.cutoff == NOW - timedelta(days=30)
    assert runtime.retention_report.deleted_result_count == 0


def test_runtime_builds_every_configured_alert_adapter(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture"),
        alerts=AlertsSettings(
            adapters=(
                ConsoleAdapterSettings(),
                HomeAssistantAdapterSettings(),
            )
        ),
    )
    monkeypatch.setenv(
        "REEFPROOF_HOME_ASSISTANT_ENDPOINT",
        "http://192.168.10.20:8123/api/webhook/reefproof",
    )
    monkeypatch.setenv("REEFPROOF_HOME_ASSISTANT_TOKEN", "test-token")

    runtime = build_runtime(settings, started_at=NOW, console_stream=io.StringIO())

    assert len(runtime.alert_coordinators) == 2
    assert {coordinator.adapter_name for coordinator in runtime.alert_coordinators} == {
        "console",
        "home_assistant",
    }


def test_runtime_rejects_yaml_selected_home_assistant_without_environment_authority(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        reefproof=ReefProofSettings(data_directory=tmp_path, mode="fixture"),
        alerts=AlertsSettings(adapters=(HomeAssistantAdapterSettings(),)),
    )
    monkeypatch.delenv("REEFPROOF_HOME_ASSISTANT_ENDPOINT", raising=False)
    monkeypatch.delenv("REEFPROOF_HOME_ASSISTANT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="REEFPROOF_HOME_ASSISTANT_ENDPOINT"):
        build_runtime(settings, started_at=NOW, console_stream=io.StringIO())


def test_service_and_access_logs_share_stdout_level_format_and_color_policy() -> None:
    configuration = _stdout_log_config(level="WARNING", use_colors=True)

    handlers = configuration["handlers"]
    formatters = configuration["formatters"]
    loggers = configuration["loggers"]
    assert isinstance(handlers, dict)
    assert isinstance(formatters, dict)
    assert isinstance(loggers, dict)
    assert handlers["server"]["stream"] == "ext://sys.stdout"
    assert handlers["access"]["stream"] == "ext://sys.stdout"
    assert formatters["server"]["fmt"] == SERVER_LOG_FORMAT
    assert formatters["access"]["fmt"] == ACCESS_LOG_FORMAT
    assert formatters["server"]["use_colors"] is True
    assert formatters["access"]["use_colors"] is True
    assert loggers["uvicorn.error"]["level"] == "WARNING"
    assert loggers["uvicorn.access"]["level"] == "WARNING"
