"""Append-only source fetch attempts separate freshness from content identity."""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authored_source_fetch_attempts",
        Column("fetch_attempt_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column(
            "source_configuration_id",
            String,
            ForeignKey("authored_source_configurations.source_configuration_id"),
            nullable=False,
        ),
        Column("fetched_at", String, nullable=False),
        Column("succeeded", Integer, nullable=False),
        Column("snapshot_hash", String),
        Column(
            "document_json",
            Text,
            CheckConstraint("json_valid(document_json)", name="document_json_valid_json"),
            nullable=False,
        ),
        CheckConstraint("succeeded IN (0, 1)", name="source_fetch_succeeded_boolean"),
    )
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER authored_source_fetch_attempts_no_{operation}
            BEFORE {operation.upper()} ON authored_source_fetch_attempts
            BEGIN
                SELECT RAISE(ABORT, 'authored source fetch attempts are immutable');
            END
            """
        )


def downgrade() -> None:
    op.drop_table("authored_source_fetch_attempts")
