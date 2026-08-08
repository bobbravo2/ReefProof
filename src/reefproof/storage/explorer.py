"""Typed, query-only SQLite schema and table projections."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

EXPLORABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "active_findings": (
        "invariant_id",
        "severity",
        "state",
        "first_seen",
        "last_seen",
        "occurrence_count",
        "last_alerted",
    ),
    "alert_attempts": (
        "attempt_id",
        "invariant_id",
        "adapter",
        "action",
        "attempted_at",
        "result",
        "duration_seconds",
        "error_category",
    ),
    "candidate_decisions": (
        "decision_id",
        "candidate_fact_id",
        "decision_kind",
        "resulting_domain_event_id",
        "decided_at",
    ),
    "candidate_facts": (
        "candidate_fact_id",
        "project_id",
        "session_id",
        "proposed_at",
    ),
    "evaluation_runs": ("evaluation_run_id", "evaluated_at", "policy_hash"),
    "finding_transitions": (
        "transition_id",
        "invariant_id",
        "kind",
        "transition_at",
        "first_seen",
        "evaluation_run_id",
    ),
    "return_flow_policy_revisions": (
        "revision_id",
        "policy_template_id",
        "revision_number",
        "created_at",
        "authoring_operator_session_id",
        "provenance",
    ),
    "interview_sessions": ("session_id", "project_id", "initiated_at"),
    "invariant_results": (
        "evaluation_run_id",
        "invariant_id",
        "result_index",
        "state",
        "severity",
    ),
    "configuration_snapshots": (
        "snapshot_hash",
        "configuration_hash",
        "annotation_hash",
        "captured_at",
    ),
    "project_domain_events": (
        "event_id",
        "project_id",
        "sequence",
        "candidate_fact_id",
        "decision_id",
        "occurred_at",
    ),
    "projects": ("project_id", "name"),
}
EXPLORABLE_TABLES = frozenset(EXPLORABLE_COLUMNS)
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_TEXT_LENGTH = 512


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CellKind(StrEnum):
    NULL = "null"
    INTEGER = "integer"
    REAL = "real"
    TEXT = "text"
    BLOB = "blob"


class DatabaseCell(FrozenModel):
    kind: CellKind
    value: str | int | float | None
    truncated: bool = False


class ColumnSchema(FrozenModel):
    position: int = Field(ge=0)
    name: str
    declared_type: str
    nullable: bool
    default_value: str | None
    primary_key_position: int = Field(ge=0)


class ForeignKeySchema(FrozenModel):
    identifier: int = Field(ge=0)
    sequence: int = Field(ge=0)
    from_column: str
    target_table: str
    target_column: str | None
    on_update: str
    on_delete: str


class IndexSchema(FrozenModel):
    name: str
    unique: bool
    columns: tuple[str, ...]


class TableSchema(FrozenModel):
    name: str
    row_count: int = Field(ge=0)
    columns: tuple[ColumnSchema, ...] = Field(min_length=1)
    foreign_keys: tuple[ForeignKeySchema, ...] = ()
    indexes: tuple[IndexSchema, ...] = ()


class DatabaseSchema(FrozenModel):
    alembic_revision: str
    integrity: str
    tables: tuple[TableSchema, ...]


class TablePage(FrozenModel):
    table_name: str
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total_rows: int = Field(ge=0)
    columns: tuple[str, ...] = Field(min_length=1)
    rows: tuple[tuple[DatabaseCell, ...], ...]
    next_offset: int | None

    @model_validator(mode="after")
    def require_rectangular_rows(self) -> Self:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("every row must match the declared column order")
        expected = self.offset + len(self.rows)
        if self.next_offset is not None and self.next_offset != expected:
            raise ValueError("next_offset must immediately follow the returned page")
        return self


class SQLiteExplorer:
    """Read approved ReefProof tables through a query-only connection."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            yield connection
        finally:
            connection.close()

    def schema(self) -> DatabaseSchema:
        with self._connection() as connection:
            revision_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            if revision_row is None:
                raise ValueError("database has no Alembic schema revision")
            integrity_row = connection.execute("PRAGMA quick_check").fetchone()
            integrity = str(integrity_row[0]) if integrity_row is not None else "UNKNOWN"
            existing = {
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
                if str(row["name"]) in EXPLORABLE_TABLES
            }
            tables = tuple(
                self._table_schema(connection, table_name) for table_name in sorted(existing)
            )
        return DatabaseSchema(
            alembic_revision=str(revision_row["version_num"]),
            integrity=integrity,
            tables=tables,
        )

    def table_page(
        self,
        table_name: str,
        *,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> TablePage:
        if offset < 0:
            raise ValueError("offset cannot be negative")
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be from 1 through {MAX_PAGE_SIZE}")
        with self._connection() as connection:
            schema = self._require_table(connection, table_name)
            identifier = _quote_identifier(schema.name)
            schema_by_name = {column.name: column for column in schema.columns}
            selected_names = EXPLORABLE_COLUMNS[table_name]
            missing = tuple(name for name in selected_names if name not in schema_by_name)
            if missing:
                raise ValueError(
                    f"approved explorer columns are absent from {table_name}: {missing}"
                )
            selected_columns = tuple(schema_by_name[name] for name in selected_names)
            total_row = connection.execute(
                f"SELECT COUNT(*) AS row_count FROM {identifier}"
            ).fetchone()
            assert total_row is not None
            total_rows = int(total_row["row_count"])
            order_columns = tuple(
                column.name
                for column in sorted(
                    selected_columns,
                    key=lambda column: column.primary_key_position,
                )
                if column.primary_key_position > 0
            ) or tuple(column.name for column in selected_columns)
            order_clause = ", ".join(_quote_identifier(name) for name in order_columns)
            select_clause = ", ".join(_quote_identifier(column.name) for column in selected_columns)
            rows = connection.execute(
                f"""
                SELECT {select_clause}
                FROM {identifier}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        rendered_rows = tuple(
            tuple(_cell(row[column.name]) for column in selected_columns) for row in rows
        )
        consumed = offset + len(rendered_rows)
        return TablePage(
            table_name=table_name,
            offset=offset,
            limit=limit,
            total_rows=total_rows,
            columns=tuple(column.name for column in selected_columns),
            rows=rendered_rows,
            next_offset=consumed if consumed < total_rows else None,
        )

    def _require_table(
        self,
        connection: sqlite3.Connection,
        table_name: str,
    ) -> TableSchema:
        if table_name not in EXPLORABLE_TABLES:
            raise KeyError(f"table is not available for inspection: {table_name}")
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if row is None:
            raise KeyError(f"table is not available for inspection: {table_name}")
        return self._table_schema(connection, table_name)

    @staticmethod
    def _table_schema(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> TableSchema:
        identifier = _quote_identifier(table_name)
        columns = tuple(
            ColumnSchema(
                position=int(row["cid"]),
                name=str(row["name"]),
                declared_type=str(row["type"]),
                nullable=not bool(row["notnull"]),
                default_value=(str(row["dflt_value"]) if row["dflt_value"] is not None else None),
                primary_key_position=int(row["pk"]),
            )
            for row in connection.execute(f"PRAGMA table_info({identifier})")
        )
        if not columns:
            raise ValueError(f"table has no inspectable columns: {table_name}")
        foreign_keys = tuple(
            ForeignKeySchema(
                identifier=int(row["id"]),
                sequence=int(row["seq"]),
                from_column=str(row["from"]),
                target_table=str(row["table"]),
                target_column=(str(row["to"]) if row["to"] is not None else None),
                on_update=str(row["on_update"]),
                on_delete=str(row["on_delete"]),
            )
            for row in connection.execute(f"PRAGMA foreign_key_list({identifier})")
        )
        indexes = []
        for row in connection.execute(f"PRAGMA index_list({identifier})"):
            index_name = str(row["name"])
            index_identifier = _quote_identifier(index_name)
            index_columns = tuple(
                str(column["name"])
                for column in connection.execute(f"PRAGMA index_info({index_identifier})")
                if column["name"] is not None
            )
            indexes.append(
                IndexSchema(
                    name=index_name,
                    unique=bool(row["unique"]),
                    columns=index_columns,
                )
            )
        count_row = connection.execute(f"SELECT COUNT(*) AS row_count FROM {identifier}").fetchone()
        assert count_row is not None
        return TableSchema(
            name=table_name,
            row_count=int(count_row["row_count"]),
            columns=columns,
            foreign_keys=foreign_keys,
            indexes=tuple(sorted(indexes, key=lambda index: index.name)),
        )


def _quote_identifier(value: str) -> str:
    if value not in EXPLORABLE_TABLES and not value.replace("_", "").isalnum():
        raise ValueError("unsafe SQLite identifier")
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _cell(value: object) -> DatabaseCell:
    if value is None:
        return DatabaseCell(kind=CellKind.NULL, value=None)
    if isinstance(value, bytes):
        return DatabaseCell(kind=CellKind.BLOB, value=f"{len(value)} bytes")
    if isinstance(value, int):
        return DatabaseCell(kind=CellKind.INTEGER, value=value)
    if isinstance(value, float):
        return DatabaseCell(kind=CellKind.REAL, value=value)
    text = str(value)
    truncated = len(text) > MAX_TEXT_LENGTH
    return DatabaseCell(
        kind=CellKind.TEXT,
        value=text[:MAX_TEXT_LENGTH] if truncated else text,
        truncated=truncated,
    )
