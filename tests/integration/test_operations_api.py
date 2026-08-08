from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import httpx

from reefproof.api import create_app
from reefproof.api.operations import LocalHostedOperations
from reefproof.service import RuntimeState
from reefproof.storage import Database

NOW = datetime.fromisoformat("2026-08-01T18:00:00-04:00")


def _state() -> RuntimeState:
    return RuntimeState.model_validate(
        {
            "started_at": NOW,
            "operating_mode": "fixture",
            "hydros_connection": "disabled",
            "mqtt_connection": "disabled",
            "last_valid_configuration_at": None,
            "last_configuration_change_at": None,
            "last_evaluation_at": None,
            "policy_loaded": True,
            "storage_writable": True,
            "unrecoverable_transport_failure": None,
            "alert_delivery_state": "unverified",
            "maximum_configuration_age_seconds": 600,
        }
    )


async def _exercise(app, method: str, path: str, *, cookie: str | None = None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        if method == "login":
            return await client.post(
                "/v1/workbench/operator-sessions", json={"bootstrap_secret": "operator-secret"}
            )
        headers = {"X-ReefProof-Operation": "desktop"}
        if cookie:
            headers["Cookie"] = f"reefproof_session={cookie}"
        return await client.request(method, path, headers=headers)


def test_hosted_operations_require_existing_operator_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "reefproof.sqlite3")
    database.migrate()
    operations = LocalHostedOperations(
        database=database,
        data_directory=database.path.parent,
        backup_directory=tmp_path / "backups",
        now=lambda: NOW,
    )
    app = create_app(
        runtime_state=_state,
        database=database,
        bootstrap_secret="operator-secret",
        hosted_operations=operations,
        now=lambda: NOW,
    )

    assert asyncio.run(_exercise(app, "GET", "/v1/operations/diagnostics")).status_code == 401
    login = asyncio.run(_exercise(app, "login", ""))
    cookie = login.cookies.get("reefproof_session")
    assert cookie is not None

    diagnostics = asyncio.run(_exercise(app, "GET", "/v1/operations/diagnostics", cookie=cookie))
    assert diagnostics.status_code == 200
    assert diagnostics.json()["status"] == "PASS"
    assert diagnostics.json()["checks"]

    backup = asyncio.run(_exercise(app, "POST", "/v1/operations/backups", cookie=cookie))
    assert backup.status_code == 201
    assert backup.json()["integrity"] == "ok"
    backup_id = backup.json()["backup_id"]
    assert str(UUID(backup_id)) == backup_id
    assert UUID(backup_id).version == 4
    assert len(backup.json()["sha256"]) == 64
    assert len(tuple((tmp_path / "backups").glob("*.sqlite3"))) == 1
    artifact = asyncio.run(
        _exercise(
            app,
            "POST",
            f"/v1/operations/backups/{backup_id}/download",
            cookie=cookie,
        )
    )
    assert artifact.status_code == 200
    assert artifact.content.startswith(b"SQLite format 3")
    assert artifact.headers["content-disposition"].endswith('filename="reefproof-backup.sqlite3"')
    assert sha256(artifact.content).hexdigest() == backup.json()["sha256"]
    assert not tuple((tmp_path / "backups").iterdir())
    replay = asyncio.run(
        _exercise(
            app,
            "POST",
            f"/v1/operations/backups/{backup_id}/download",
            cookie=cookie,
        )
    )
    assert replay.status_code == 404
    assert database.api_mutation_audit_count("/v1/operations/diagnostics") == 0
    assert database.api_mutation_audit_count("/v1/operations/backups") == 1
    assert database.api_mutation_audit_count("/v1/operations/backups/{backup_id}/download") == 2


def test_hosted_restart_fails_closed_without_supervisor(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = create_app(
        runtime_state=_state,
        database=database,
        bootstrap_secret="operator-secret",
        hosted_operations=LocalHostedOperations(
            database=database,
            data_directory=database.path.parent,
            backup_directory=tmp_path / "backups",
            now=lambda: NOW,
        ),
        now=lambda: NOW,
    )
    login = asyncio.run(_exercise(app, "login", ""))
    cookie = login.cookies.get("reefproof_session")
    response = asyncio.run(_exercise(app, "POST", "/v1/operations/restart", cookie=cookie))
    assert response.status_code == 503
    assert response.json()["detail"] == "hosted ReefProof supervisor is not configured"


def test_hosted_backup_ids_expire_and_malformed_ids_are_rejected(tmp_path: Path) -> None:
    current = [NOW]
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    operations = LocalHostedOperations(
        database=database,
        data_directory=tmp_path,
        backup_directory=tmp_path / "backups",
        now=lambda: current[0],
        backup_retention=timedelta(minutes=5),
    )
    app = create_app(
        runtime_state=_state,
        database=database,
        bootstrap_secret="operator-secret",
        hosted_operations=operations,
        now=lambda: current[0],
    )
    login = asyncio.run(_exercise(app, "login", ""))
    cookie = login.cookies.get("reefproof_session")
    backup = asyncio.run(_exercise(app, "POST", "/v1/operations/backups", cookie=cookie))
    current[0] = NOW + timedelta(minutes=6)

    malformed = asyncio.run(
        _exercise(app, "POST", "/v1/operations/backups/not-a-uuid/download", cookie=cookie)
    )
    expired = asyncio.run(
        _exercise(
            app,
            "POST",
            f"/v1/operations/backups/{backup.json()['backup_id']}/download",
            cookie=cookie,
        )
    )
    assert malformed.status_code == 422
    assert expired.status_code == 404
    assert not tuple((tmp_path / "backups").iterdir())


def test_restart_cleanup_expires_only_owned_staged_backup_files(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    backup_directory = tmp_path / "backups"
    original = LocalHostedOperations(
        database=database,
        data_directory=tmp_path,
        backup_directory=backup_directory,
        now=lambda: NOW,
        backup_retention=timedelta(minutes=5),
    )
    original.backup()
    staged = tuple(backup_directory.glob("staged-*.sqlite3"))
    assert len(staged) == 1
    unrelated = backup_directory / "operator-kept.sqlite3"
    unrelated.write_bytes(b"keep")

    LocalHostedOperations(
        database=database,
        data_directory=tmp_path,
        backup_directory=backup_directory,
        now=lambda: NOW + timedelta(minutes=6),
        backup_retention=timedelta(minutes=5),
    )

    assert not staged[0].exists()
    assert unrelated.read_bytes() == b"keep"


def test_hosted_restart_uses_only_the_injected_supervisor_and_is_audited(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    requested: list[bool] = []
    app = create_app(
        runtime_state=_state,
        database=database,
        bootstrap_secret="operator-secret",
        hosted_operations=LocalHostedOperations(
            database=database,
            data_directory=database.path.parent,
            backup_directory=tmp_path / "backups",
            now=lambda: NOW,
            restart_service=lambda: requested.append(True) or "scheduled",
        ),
        now=lambda: NOW,
    )
    login = asyncio.run(_exercise(app, "login", ""))
    cookie = login.cookies.get("reefproof_session")
    assert cookie is not None

    missing_marker = asyncio.run(
        _request_without_operation_marker(app, "POST", "/v1/operations/restart", cookie)
    )
    assert missing_marker.status_code == 403
    assert requested == []

    response = asyncio.run(_exercise(app, "POST", "/v1/operations/restart", cookie=cookie))
    assert response.status_code == 202
    assert response.json() == {
        "status": "ACCEPTED",
        "operation": "restart",
        "detail": "scheduled",
    }
    assert requested == [True]
    assert database.api_mutation_audit_count("/v1/operations/restart") == 2


async def _request_without_operation_marker(app, method: str, path: str, cookie: str):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.request(
            method,
            path,
            headers={"Cookie": f"reefproof_session={cookie}"},
        )
