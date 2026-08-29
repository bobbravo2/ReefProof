"""Allow explicit non-Sheet identity evidence without fabricated import provenance."""

from __future__ import annotations

from alembic import op
from sqlalchemy import CheckConstraint, Column, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.schema import SchemaItem

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _create_table(name: str, *, import_nullable: bool, include_evidence: bool = True) -> None:
    columns: list[SchemaItem] = [
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
            nullable=import_nullable,
        ),
    ]
    if include_evidence:
        columns.append(Column("evidence_reference", String))
    columns.extend(
        [
            Column("accepted_at", String, nullable=False),
            Column(
                "document_json",
                Text,
                CheckConstraint("json_valid(document_json)", name=f"{name}_document_json_valid"),
                nullable=False,
            ),
            UniqueConstraint(
                "project_id",
                "source_system",
                "source_instance",
                "namespace",
                "external_value",
                name=f"{name}_unique_source_value",
            ),
        ]
    )
    op.create_table(name, *columns)


def _create_immutability_triggers() -> None:
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


def upgrade() -> None:
    _create_table("external_identity_bindings_v2", import_nullable=True)
    op.execute(
        """
        INSERT INTO external_identity_bindings_v2(
            binding_id, project_id, source_system, source_instance, namespace,
            external_value, canonical_subject_id, import_batch_id,
            evidence_reference, accepted_at, document_json
        )
        SELECT binding_id, project_id, source_system, source_instance, namespace,
               external_value, canonical_subject_id, import_batch_id,
               NULL, accepted_at, document_json
        FROM external_identity_bindings
        """
    )
    op.execute("DROP TRIGGER external_identity_bindings_no_update")
    op.execute("DROP TRIGGER external_identity_bindings_no_delete")
    op.drop_table("external_identity_bindings")
    op.rename_table("external_identity_bindings_v2", "external_identity_bindings")
    _create_immutability_triggers()


def downgrade() -> None:
    non_sheet_count = (
        op.get_bind()
        .execute(
            text("SELECT COUNT(*) FROM external_identity_bindings WHERE import_batch_id IS NULL")
        )
        .scalar_one()
    )
    if non_sheet_count:
        raise RuntimeError(
            "cannot downgrade ReefProof schema 0006 while explicit non-Sheet identity "
            "bindings exist; preserving immutable evidence requires schema 0006"
        )
    _create_table(
        "external_identity_bindings_v1",
        import_nullable=False,
        include_evidence=False,
    )
    op.execute(
        """
        INSERT INTO external_identity_bindings_v1(
            binding_id, project_id, source_system, source_instance, namespace,
            external_value, canonical_subject_id, import_batch_id,
            accepted_at, document_json
        )
        SELECT binding_id, project_id, source_system, source_instance, namespace,
               external_value, canonical_subject_id, import_batch_id,
               accepted_at, document_json
        FROM external_identity_bindings
        """
    )
    op.execute("DROP TRIGGER external_identity_bindings_no_update")
    op.execute("DROP TRIGGER external_identity_bindings_no_delete")
    op.drop_table("external_identity_bindings")
    op.rename_table("external_identity_bindings_v1", "external_identity_bindings")
    _create_immutability_triggers()
