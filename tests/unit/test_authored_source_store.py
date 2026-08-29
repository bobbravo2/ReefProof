from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from reefproof.authored_sources import (
    AuthoredSourceConfiguration,
    AuthoredSourceSnapshot,
    AuthoredSourceStore,
    AuthoredSourceTab,
    SourceTabName,
    normalize_source_snapshot,
)
from reefproof.authored_sources.models import SOURCE_TAB_NAMES, source_snapshot_hash
from reefproof.project_state import Project
from reefproof.project_store import ProjectStore
from reefproof.storage import DATABASE_SCHEMA_VERSION, Database

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _alembic(path: Path) -> Config:
    configuration = Config()
    configuration.set_main_option(
        "script_location",
        str(Path("src/reefproof/storage/migrations").resolve()),
    )
    configuration.set_main_option("sqlalchemy.url", f"sqlite:///{path.resolve().as_posix()}")
    return configuration


def _snapshot() -> AuthoredSourceSnapshot:
    identifiers = {
        SourceTabName.BOM: "BOM_ID",
        SourceTabName.DOMAINS: "DOMAIN_ID",
        SourceTabName.POWER: "POWER_ID",
        SourceTabName.DEVICE_INTERFACES: "INTERFACE_ID",
        SourceTabName.OUTPUTS: "OUTPUT_ID",
        SourceTabName.MODES: "MODE_ID",
    }
    tabs = tuple(
        AuthoredSourceTab(
            name=name,
            source_range=f"'{name.value}'!A1:ZZ10000",
            rows=((identifiers[name],), (f"{name.value}-1",)),
        )
        for name in SOURCE_TAB_NAMES
    )
    return AuthoredSourceSnapshot(
        source_snapshot_id="snapshot-1",
        source_alias="primary-design",
        spreadsheet_id="sheet-fixture",
        spreadsheet_title="Primary Reef System",
        fetched_at=NOW,
        tabs=tabs,
        snapshot_hash=source_snapshot_hash(tabs),
    )


def _store(path: Path) -> AuthoredSourceStore:
    database = Database(path)
    database.migrate()
    ProjectStore(path).record_project(
        Project(
            project_id="primary-reef-system",
            name="Primary Reef System",
            acceptance_authority_principal_id="local-acceptance-authority",
            created_at=NOW,
        )
    )
    return AuthoredSourceStore(path)


def test_current_schema_persists_source_evidence_without_canonical_facts(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    store = _store(path)
    configuration = AuthoredSourceConfiguration(
        source_configuration_id="source-config-1",
        project_id="primary-reef-system",
        source_alias="primary-design",
        spreadsheet_id="sheet-fixture",
        configured_at=NOW,
        freshness_seconds=3600,
    )
    snapshot = _snapshot()
    batch = normalize_source_snapshot(snapshot)

    assert Database(path).schema_version() == DATABASE_SCHEMA_VERSION == 6
    assert store.record_configuration(configuration)
    assert store.record_import(
        project_id="primary-reef-system",
        source_configuration_id=configuration.source_configuration_id,
        snapshot=snapshot,
        batch=batch,
    )
    assert not store.record_configuration(configuration)
    assert not store.record_import(
        project_id="primary-reef-system",
        source_configuration_id=configuration.source_configuration_id,
        snapshot=snapshot,
        batch=batch,
    )
    refreshed_at = NOW + timedelta(minutes=5)
    assert not store.record_import(
        project_id="primary-reef-system",
        source_configuration_id=configuration.source_configuration_id,
        snapshot=snapshot.model_copy(update={"fetched_at": refreshed_at}),
        batch=batch.model_copy(update={"fetched_at": refreshed_at}),
    )
    assert store.latest_successful_fetch_at("primary-reef-system") == refreshed_at
    assert store.latest_import("primary-reef-system") == batch
    assert ProjectStore(path).replay("primary-reef-system").facts == ()


def test_schema_0006_upgrades_existing_0005_identity_table(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    configuration = _alembic(path)
    command.upgrade(configuration, "0005")

    command.upgrade(configuration, "0006")

    with sqlite3.connect(path) as connection:
        columns = {
            str(row[1]): bool(row[3])
            for row in connection.execute("PRAGMA table_info(external_identity_bindings)")
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == ("0006",)
    assert columns["import_batch_id"] is False
    assert columns["evidence_reference"] is False


def test_schema_0006_downgrade_refuses_to_discard_non_sheet_identity_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO external_identity_bindings(
                binding_id, project_id, source_system, source_instance, namespace,
                external_value, canonical_subject_id, import_batch_id,
                evidence_reference, accepted_at, document_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                "binding-observed",
                "primary-reef-system",
                "hydros",
                "sha256:observed",
                "reefproof_id",
                "RP.CONTROLLER.fixture",
                "rp:primary-reef-system:device:dev-1",
                "onsite identity comparison",
                NOW.isoformat(),
                '{"fixture":"immutable observed identity"}',
            ),
        )

    with pytest.raises(RuntimeError, match="preserving immutable evidence"):
        command.downgrade(_alembic(path), "0005")

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0006",)
        assert connection.execute(
            "SELECT evidence_reference FROM external_identity_bindings"
        ).fetchone() == ("onsite identity comparison",)


def test_authored_source_evidence_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    store = _store(path)
    configuration = AuthoredSourceConfiguration(
        source_configuration_id="source-config-1",
        project_id="primary-reef-system",
        source_alias="primary-design",
        spreadsheet_id="sheet-fixture",
        configured_at=NOW,
        freshness_seconds=3600,
    )
    store.record_configuration(configuration)

    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE authored_source_configurations SET source_alias = 'changed' "
            "WHERE source_configuration_id = 'source-config-1'"
        )
