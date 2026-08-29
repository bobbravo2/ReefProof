"""Append-only external source identities bound to canonical subjects."""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Text, UniqueConstraint

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_identity_bindings",
        Column("binding_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("source_system", String, nullable=False),
        Column("source_instance", String, nullable=False),
        Column("namespace", String, nullable=False),
        Column("external_value", String, nullable=False),
        Column("canonical_subject_id", String, nullable=False),
        Column(
            "import_batch_id",
            String,
            ForeignKey("authored_import_batches.import_batch_id"),
            nullable=False,
        ),
        Column("accepted_at", String, nullable=False),
        Column(
            "document_json",
            Text,
            CheckConstraint("json_valid(document_json)", name="document_json_valid_json"),
            nullable=False,
        ),
        UniqueConstraint(
            "project_id",
            "source_system",
            "source_instance",
            "namespace",
            "external_value",
            name="external_identity_unique_source_value",
        ),
    )
    for operation in ("update", "delete"):
        op.execute(
            f"""
            CREATE TRIGGER external_identity_bindings_no_{operation}
            BEFORE {operation.upper()} ON external_identity_bindings
            BEGIN
                SELECT RAISE(ABORT, 'external identity bindings are immutable');
            END
            """
        )


def downgrade() -> None:
    op.drop_table("external_identity_bindings")
