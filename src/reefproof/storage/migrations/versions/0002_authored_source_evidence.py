"""Immutable authored-source configuration, snapshot, and import evidence."""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text, UniqueConstraint

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TABLES = (
    "authored_source_configurations",
    "authored_source_snapshots",
    "authored_import_batches",
)


def _document() -> Column[str]:
    return Column(
        "document_json",
        Text,
        CheckConstraint("json_valid(document_json)", name="document_json_valid_json"),
        nullable=False,
    )


def _immutable(table: str) -> None:
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_{operation}
            BEFORE {operation.upper()} ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table} records are immutable');
            END
            """
        )


def upgrade() -> None:
    op.create_table(
        "authored_source_configurations",
        Column("source_configuration_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("source_alias", String, nullable=False),
        Column("spreadsheet_id", String, nullable=False),
        Column("configured_at", String, nullable=False),
        _document(),
        UniqueConstraint(
            "project_id",
            "source_alias",
            "spreadsheet_id",
            "configured_at",
            name="authored_source_configuration_identity",
        ),
    )
    op.create_table(
        "authored_source_snapshots",
        Column("source_snapshot_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column(
            "source_configuration_id",
            String,
            ForeignKey("authored_source_configurations.source_configuration_id"),
            nullable=False,
        ),
        Column("snapshot_hash", String, nullable=False),
        Column("fetched_at", String, nullable=False),
        _document(),
        CheckConstraint(
            "snapshot_hash GLOB 'sha256:[0-9a-f]*' AND length(snapshot_hash) = 71",
            name="authored_source_snapshot_hash_shape",
        ),
        UniqueConstraint(
            "project_id",
            "source_configuration_id",
            "snapshot_hash",
            name="authored_source_snapshot_content",
        ),
    )
    op.create_table(
        "authored_import_batches",
        Column("import_batch_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column(
            "source_snapshot_id",
            String,
            ForeignKey("authored_source_snapshots.source_snapshot_id"),
            nullable=False,
            unique=True,
        ),
        Column("normalized_content_hash", String, nullable=False),
        Column("valid", Integer, nullable=False),
        Column("fetched_at", String, nullable=False),
        _document(),
        CheckConstraint("valid IN (0, 1)", name="authored_import_batch_valid_boolean"),
        CheckConstraint(
            "normalized_content_hash GLOB 'sha256:[0-9a-f]*' "
            "AND length(normalized_content_hash) = 71",
            name="authored_import_normalized_hash_shape",
        ),
    )
    for table in _TABLES:
        _immutable(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
