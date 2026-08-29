"""Append-only commissioning verification and failure-mode evidence."""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


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
        "commissioning_verifications",
        Column("verification_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("device_id", String, nullable=False),
        Column("kind", String, nullable=False),
        Column("outcome", String, nullable=False),
        Column("verified_at", String, nullable=False),
        _document(),
    )
    op.create_table(
        "failure_mode_dispositions",
        Column("disposition_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("device_id", String, nullable=False),
        Column("failure_mode_id", String, nullable=False),
        Column("disposition", String, nullable=False),
        Column("decided_at", String, nullable=False),
        _document(),
    )
    _immutable("commissioning_verifications")
    _immutable("failure_mode_dispositions")


def downgrade() -> None:
    op.drop_table("failure_mode_dispositions")
    op.drop_table("commissioning_verifications")
