"""Read-only SQLite explorer tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from reefproof.storage import Database
from reefproof.storage.explorer import (
    EXPLORABLE_COLUMNS,
    EXPLORABLE_TABLES,
    MAX_PAGE_SIZE,
    CellKind,
    SQLiteExplorer,
)

SNAPSHOT_A = f"sha256:{'a' * 64}"
SNAPSHOT_B = f"sha256:{'b' * 64}"
SNAPSHOT_C = f"sha256:{'c' * 64}"
CONFIGURATION_HASH = f"sha256:{'d' * 64}"
ANNOTATION_HASH = f"sha256:{'e' * 64}"


def _database(path: Path) -> Database:
    database = Database(path)
    database.migrate()
    return database


def test_schema_lists_only_allowlisted_application_tables(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")

    schema = SQLiteExplorer(database.path).schema()

    assert schema.alembic_revision
    assert schema.integrity == "ok"
    assert schema.tables
    assert {table.name for table in schema.tables} <= EXPLORABLE_TABLES
    assert "alembic_version" not in {table.name for table in schema.tables}
    assert "sqlite_sequence" not in {table.name for table in schema.tables}
    projects = next(table for table in schema.tables if table.name == "projects")
    assert [column.name for column in projects.columns][:3] == [
        "project_id",
        "name",
        "acceptance_authority_principal_id",
    ]
    assert projects.columns[0].primary_key_position == 1


def test_table_pages_are_stable_bounded_and_type_explicit(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    with sqlite3.connect(database.path) as connection:
        connection.executemany(
            """
            INSERT INTO configuration_snapshots(
                snapshot_hash, configuration_hash, annotation_hash,
                captured_at, document_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    SNAPSHOT_C,
                    CONFIGURATION_HASH,
                    ANNOTATION_HASH,
                    "2026-07-25T03:00:00Z",
                    "{}",
                ),
                (
                    SNAPSHOT_A,
                    CONFIGURATION_HASH,
                    ANNOTATION_HASH,
                    "2026-07-25T01:00:00Z",
                    "{}",
                ),
                (
                    SNAPSHOT_B,
                    CONFIGURATION_HASH,
                    ANNOTATION_HASH,
                    "2026-07-25T02:00:00Z",
                    json.dumps("x" * 700),
                ),
            ),
        )

    explorer = SQLiteExplorer(database.path)
    first = explorer.table_page("configuration_snapshots", limit=2)
    second = explorer.table_page(
        "configuration_snapshots",
        offset=first.next_offset or 0,
        limit=2,
    )

    assert first.total_rows == 3
    assert first.next_offset == 2
    assert [row[0].value for row in first.rows] == [SNAPSHOT_A, SNAPSHOT_B]
    assert second.next_offset is None
    assert second.rows[0][0].value == SNAPSHOT_C
    configuration_index = first.columns.index("configuration_hash")
    assert first.rows[1][configuration_index].kind is CellKind.TEXT
    assert not first.rows[1][configuration_index].truncated


def test_row_projection_excludes_payloads_and_future_columns(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    with sqlite3.connect(database.path) as connection:
        connection.execute("ALTER TABLE configuration_snapshots ADD COLUMN future_secret TEXT")
        connection.execute(
            """
            INSERT INTO configuration_snapshots(
                snapshot_hash, configuration_hash, annotation_hash,
                captured_at, document_json, future_secret
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                SNAPSHOT_A,
                CONFIGURATION_HASH,
                ANNOTATION_HASH,
                "2026-07-25T04:00:00Z",
                '{"private":"DOCUMENT-SENTINEL"}',
                "FUTURE-SECRET-SENTINEL",
            ),
        )

    explorer = SQLiteExplorer(database.path)
    schema = explorer.schema()
    page = explorer.table_page("configuration_snapshots")
    snapshot_schema = next(
        table for table in schema.tables if table.name == "configuration_snapshots"
    )

    assert "future_secret" in {column.name for column in snapshot_schema.columns}
    assert page.columns == EXPLORABLE_COLUMNS["configuration_snapshots"]
    rendered = page.model_dump_json()
    assert "document_json" not in rendered
    assert "DOCUMENT-SENTINEL" not in rendered
    assert "future_secret" not in rendered
    assert "FUTURE-SECRET-SENTINEL" not in rendered


@pytest.mark.parametrize(
    ("table_name", "offset", "limit"),
    (
        ("sqlite_master", 0, 10),
        ("alembic_version", 0, 10),
        ("projects; DELETE FROM projects", 0, 10),
        ("projects", -1, 10),
        ("projects", 0, 0),
        ("projects", 0, MAX_PAGE_SIZE + 1),
    ),
)
def test_unknown_internal_injected_and_unbounded_requests_fail_closed(
    tmp_path: Path,
    table_name: str,
    offset: int,
    limit: int,
) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    explorer = SQLiteExplorer(database.path)

    with pytest.raises((KeyError, ValueError)):
        explorer.table_page(table_name, offset=offset, limit=limit)


def test_explorer_source_has_no_mutation_or_arbitrary_sql_surface() -> None:
    source = Path("src/reefproof/storage/explorer.py").read_text()

    assert "mode=ro" in source
    assert "PRAGMA query_only = ON" in source
    assert "executescript" not in source
    assert " INSERT " not in source
    assert " UPDATE " not in source
    assert " DELETE " not in source
    assert " ATTACH " not in source
