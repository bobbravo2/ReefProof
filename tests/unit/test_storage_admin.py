from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reefproof.cli import app
from reefproof.rules import ReturnFlowPolicyInputs, ReturnFlowPolicyRevision
from reefproof.service.infra_smoke import database_path
from reefproof.storage import Database

NOW = datetime(2026, 7, 25, 22, 0, tzinfo=UTC)
AUTHOR_SESSION_ID = "12345678-abcd-4234-8234-123456789abc"
runner = CliRunner()


def _database(path: Path) -> tuple[Database, ReturnFlowPolicyRevision]:
    database = Database(path)
    database.migrate()
    revision = database.record_return_flow_policy_revision(
        ReturnFlowPolicyInputs(
            tank_volume_gallons=120,
            pump_rated_flow_gph=1000,
            delivered_flow_gph=700,
            minimum_turnover_per_hour=5,
        ),
        created_at=NOW,
        authoring_operator_session_id=AUTHOR_SESSION_ID,
    )
    return database, revision


def test_backup_includes_committed_wal_and_restore_reproduces_rule(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    source, revision = _database(source_path)
    writer = sqlite3.connect(source_path)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute(
        """
        INSERT INTO configuration_snapshots(
            snapshot_hash, configuration_hash, annotation_hash, captured_at, document_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            f"sha256:{'c' * 64}",
            f"sha256:{'a' * 64}",
            f"sha256:{'b' * 64}",
            NOW.isoformat(),
            "{}",
        ),
    )
    writer.commit()
    assert source_path.with_name(f"{source_path.name}-wal").is_file()

    backup_path = tmp_path / "backup.sqlite3"
    source.backup_to(backup_path)
    writer.close()

    backup = Database(backup_path)
    assert backup.integrity_check() == "ok"
    assert backup.inspect_evidence()["counts"] == {
        "snapshots": 1,
        "evaluations": 0,
        "active_findings": 0,
        "finding_transitions": 0,
        "rule_revisions": 1,
        "alert_attempts": 0,
        "projects": 0,
        "sessions": 0,
        "candidate_facts": 0,
        "candidate_decisions": 0,
        "project_domain_events": 0,
        "project_trust_events": 0,
    }
    assert backup.latest_return_flow_policy_revision() == revision

    restored_path = tmp_path / "restored.sqlite3"
    restored = Database.restore_to(backup_path, restored_path)
    assert restored.latest_return_flow_policy_revision() == revision
    assert restored.inspect_evidence() == backup.inspect_evidence()


def test_backup_restore_never_overwrite_and_reject_invalid_source(tmp_path: Path) -> None:
    source, _ = _database(tmp_path / "source.sqlite3")
    existing = tmp_path / "existing.sqlite3"
    existing.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        source.backup_to(existing)
    assert existing.read_text(encoding="utf-8") == "keep"

    with pytest.raises(FileExistsError):
        Database.restore_to(source.path, existing)
    assert existing.read_text(encoding="utf-8") == "keep"

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    restore_target = tmp_path / "corrupt-restore.sqlite3"
    with pytest.raises(sqlite3.DatabaseError):
        Database.restore_to(corrupt, restore_target)
    assert not restore_target.exists()

    unsupported = tmp_path / "unsupported.sqlite3"
    with sqlite3.connect(unsupported) as connection:
        connection.execute("CREATE TABLE alembic_version(version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('9999')")
    unsupported_target = tmp_path / "unsupported-restore.sqlite3"
    with pytest.raises(ValueError, match="unsupported backup schema"):
        Database.restore_to(unsupported, unsupported_target)
    assert not unsupported_target.exists()


def test_inspection_connection_is_query_only_and_cannot_mutate_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database, revision = _database(path)

    document = database.inspect_evidence()

    categories = document["categories"]
    assert isinstance(categories, dict)
    assert set(categories) == {
        "snapshots",
        "evaluations",
        "findings",
        "rule_revisions",
        "alert_attempts",
        "project_state",
    }
    with database._read_connection() as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM return_flow_policy_revisions")
    assert database.latest_return_flow_policy_revision() == revision


def test_storage_cli_inspect_backup_and_restore_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_directory = tmp_path / "data"
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))
    source, revision = _database(database_path(data_directory))
    del source
    runner = CliRunner()

    inspection = runner.invoke(app, ["database", "inspect"])
    backup_path = tmp_path / "backup.sqlite3"
    backup = runner.invoke(app, ["database", "backup", str(backup_path)])
    restored_path = tmp_path / "restored.sqlite3"
    restore = runner.invoke(
        app,
        ["database", "restore", str(backup_path), str(restored_path)],
    )

    assert inspection.exit_code == 0, inspection.stdout
    inspection_document = json.loads(inspection.stdout)
    assert inspection_document["status"] == "PASS"
    assert inspection_document["counts"]["rule_revisions"] == 1
    assert set(inspection_document["categories"]) == {
        "snapshots",
        "evaluations",
        "findings",
        "rule_revisions",
        "alert_attempts",
        "project_state",
    }
    assert backup.exit_code == 0, backup.stdout
    assert json.loads(backup.stdout)["latest_rule_revision"] == revision.model_dump(mode="json")
    assert restore.exit_code == 0, restore.stdout
    assert json.loads(restore.stdout)["latest_rule_revision"] == revision.model_dump(mode="json")
    assert Database(restored_path).latest_return_flow_policy_revision() == revision


def test_storage_cli_generates_rotating_destination_under_configured_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_directory = tmp_path / "data"
    backup_root = tmp_path / "mounted-backups"
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))
    monkeypatch.setenv("REEFPROOF_BACKUP_DIRECTORY", str(backup_root))
    source, _ = _database(database_path(data_directory))

    result = runner.invoke(app, ["database", "backup"])

    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    destination = Path(document["destination"])
    assert destination.parent.parent == backup_root
    assert len(destination.parent.name) == 10
    assert destination.name.startswith("reefproof-")
    assert Database(destination).integrity_check() == "ok"
    assert source.integrity_check() == "ok"
