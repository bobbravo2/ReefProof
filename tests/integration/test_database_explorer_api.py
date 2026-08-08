"""Authenticated read-only database explorer API tests."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI

from reefproof.api import create_app
from reefproof.service import RuntimeState
from reefproof.storage import Database

NOW = datetime(2026, 7, 25, 23, 30, tzinfo=UTC)
BOOTSTRAP_SECRET = "test-database-explorer-secret"


def _unreachable_runtime_state() -> RuntimeState:
    raise AssertionError("database explorer must not inspect runtime state")


def _app(tmp_path: Path) -> tuple[FastAPI, Database]:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    return (
        create_app(
            runtime_state=_unreachable_runtime_state,
            database=database,
            now=lambda: NOW,
            bootstrap_secret=BOOTSTRAP_SECRET,
        ),
        database,
    )


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=headers, json=json)


def _session_headers(app: FastAPI) -> dict[str, str]:
    response = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/operator-sessions",
            json={"bootstrap_secret": BOOTSTRAP_SECRET},
        )
    )
    assert response.status_code == 201
    cookie = response.cookies.get("reefproof_session")
    assert cookie is not None
    return {"Cookie": f"reefproof_session={cookie}"}


def test_database_schema_and_rows_require_a_valid_session(tmp_path: Path) -> None:
    app, _database = _app(tmp_path)

    assert asyncio.run(_request(app, "GET", "/v1/database/schema")).status_code == 401
    assert (
        asyncio.run(
            _request(
                app,
                "GET",
                "/v1/database/schema",
                headers={"Cookie": "reefproof_session=malformed"},
            )
        ).status_code
        == 401
    )

    headers = _session_headers(app)
    schema = asyncio.run(_request(app, "GET", "/v1/database/schema", headers=headers))
    assert schema.status_code == 200
    assert schema.json()["integrity"] == "ok"
    assert {table["name"] for table in schema.json()["tables"]}


def test_database_rows_exclude_payloads_and_are_bounded(tmp_path: Path) -> None:
    app, database = _app(tmp_path)
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            """
            INSERT INTO configuration_snapshots(
                snapshot_hash, configuration_hash, annotation_hash,
                captured_at, document_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"sha256:{'a' * 64}",
                f"sha256:{'b' * 64}",
                f"sha256:{'c' * 64}",
                "2026-07-25T23:00:00Z",
                '{"private":"PRIVATE-DOCUMENT-SENTINEL"}',
            ),
        )

    headers = _session_headers(app)
    response = asyncio.run(
        _request(
            app,
            "GET",
            "/v1/database/tables/configuration_snapshots?limit=1&offset=0",
            headers=headers,
        )
    )

    assert response.status_code == 200
    page = response.json()
    assert page["total_rows"] == 1
    assert page["limit"] == 1
    assert "document_json" not in page["columns"]
    assert "PRIVATE-DOCUMENT-SENTINEL" not in response.text
    assert (
        asyncio.run(
            _request(
                app,
                "GET",
                "/v1/database/tables/configuration_snapshots?limit=101",
                headers=headers,
            )
        ).status_code
        == 422
    )


def test_database_api_fails_closed_for_tables_and_mutation_verbs(tmp_path: Path) -> None:
    app, _database = _app(tmp_path)
    headers = _session_headers(app)

    for table_name in ("sqlite_master", "alembic_version", "unknown"):
        response = asyncio.run(
            _request(
                app,
                "GET",
                f"/v1/database/tables/{table_name}",
                headers=headers,
            )
        )
        assert response.status_code == 404

    schema = app.openapi()
    assert set(schema["paths"]["/v1/database/schema"]) == {"get"}
    assert set(schema["paths"]["/v1/database/tables/{table_name}"]) == {"get"}
    parameters = schema["paths"]["/v1/database/tables/{table_name}"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {
        "table_name",
        "offset",
        "limit",
    }
    assert schema["paths"]["/v1/database/tables/{table_name}"]["get"]["security"] == [
        {"operatorSession": []}
    ]
    assert "requestBody" not in schema["paths"]["/v1/database/tables/{table_name}"]["get"]

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = asyncio.run(
            _request(
                app,
                method,
                "/v1/database/tables/projects",
                headers=headers,
            )
        )
        assert response.status_code == 405
