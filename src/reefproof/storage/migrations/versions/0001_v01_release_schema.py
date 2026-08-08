"""Fresh-install ReefProof v0.1 SQLite release schema."""

from __future__ import annotations

from alembic import op
from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = (
    "return_flow_policy_revisions",
    "projects",
    "interview_sessions",
    "candidate_facts",
    "candidate_decisions",
    "project_domain_events",
    "project_trust_events",
    "api_mutation_audit",
)


def _json_document(name: str = "document_json") -> Column[str]:
    return Column(
        name,
        Text,
        CheckConstraint(f"json_valid({name})", name=f"{name}_valid_json"),
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
        "configuration_snapshots",
        Column("snapshot_hash", String, primary_key=True),
        Column("configuration_hash", String, nullable=False),
        Column("annotation_hash", String, nullable=False),
        Column("captured_at", String, nullable=False),
        _json_document(),
        CheckConstraint(
            "snapshot_hash GLOB 'sha256:[0-9a-f]*' AND length(snapshot_hash) = 71",
            name="snapshot_hash_shape",
        ),
        CheckConstraint(
            "configuration_hash GLOB 'sha256:[0-9a-f]*' AND length(configuration_hash) = 71",
            name="configuration_hash_shape",
        ),
        CheckConstraint(
            "annotation_hash GLOB 'sha256:[0-9a-f]*' AND length(annotation_hash) = 71",
            name="annotation_hash_shape",
        ),
    )
    op.create_table(
        "evaluation_runs",
        Column("evaluation_run_id", String, primary_key=True),
        Column("evaluated_at", String, nullable=False),
        Column("policy_hash", String, nullable=False),
        Column("result_count", Integer, nullable=False, server_default="0"),
        Column("pass_count", Integer, nullable=False, server_default="0"),
        Column("fail_count", Integer, nullable=False, server_default="0"),
        Column("unknown_count", Integer, nullable=False, server_default="0"),
        CheckConstraint("result_count >= 0", name="evaluation_result_count_nonnegative"),
        CheckConstraint("pass_count >= 0", name="evaluation_pass_count_nonnegative"),
        CheckConstraint("fail_count >= 0", name="evaluation_fail_count_nonnegative"),
        CheckConstraint("unknown_count >= 0", name="evaluation_unknown_count_nonnegative"),
        CheckConstraint(
            "result_count = pass_count + fail_count + unknown_count",
            name="evaluation_summary_balanced",
        ),
    )
    op.create_table(
        "invariant_results",
        Column(
            "evaluation_run_id",
            String,
            ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("invariant_id", String, primary_key=True),
        Column("result_index", Integer, nullable=False),
        Column("state", String, nullable=False),
        Column("severity", String, nullable=False),
        _json_document(),
        CheckConstraint("result_index >= 0", name="result_index_nonnegative"),
        CheckConstraint("state IN ('PASS', 'FAIL', 'UNKNOWN')", name="invariant_result_state"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'high', 'critical')",
            name="invariant_result_severity",
        ),
    )
    op.create_table(
        "active_findings",
        Column("invariant_id", String, primary_key=True),
        Column("severity", String, nullable=False),
        Column("state", String, nullable=False),
        Column("first_seen", String, nullable=False),
        Column("last_seen", String, nullable=False),
        Column("occurrence_count", Integer, nullable=False),
        Column("last_alerted", String),
        _json_document("result_json"),
        CheckConstraint("occurrence_count > 0", name="occurrence_count_positive"),
        CheckConstraint("state IN ('FAIL', 'UNKNOWN')", name="active_finding_state"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'high', 'critical')",
            name="active_finding_severity",
        ),
    )
    op.create_table(
        "finding_transitions",
        Column("transition_id", Integer, primary_key=True, autoincrement=True),
        Column("invariant_id", String, nullable=False),
        Column("kind", String, nullable=False),
        Column("transition_at", String, nullable=False),
        Column("first_seen", String, nullable=False),
        Column(
            "evaluation_run_id",
            String,
            ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        _json_document("result_json"),
        CheckConstraint("kind IN ('opened', 'recovered')", name="finding_transition_kind"),
    )
    op.create_index(
        "finding_transitions_invariant_time",
        "finding_transitions",
        ["invariant_id", "transition_at"],
    )
    op.create_table(
        "alert_attempts",
        Column("attempt_id", String, primary_key=True),
        Column("invariant_id", String, nullable=False),
        Column("adapter", String, nullable=False),
        Column("action", String, nullable=False),
        Column("attempted_at", String, nullable=False),
        Column("result", String, nullable=False),
        Column("duration_seconds", Float, nullable=False),
        Column("error_category", String),
        CheckConstraint("result IN ('success', 'failure')", name="alert_attempt_result"),
        CheckConstraint("duration_seconds >= 0", name="alert_duration_nonnegative"),
    )
    op.create_index(
        "alert_attempts_invariant_time",
        "alert_attempts",
        ["invariant_id", "attempted_at"],
    )
    op.create_table(
        "return_flow_policy_revisions",
        Column("revision_id", String, primary_key=True),
        Column("policy_template_id", String, nullable=False),
        Column("revision_number", Integer, nullable=False),
        Column("created_at", String, nullable=False),
        Column("authoring_operator_session_id", String, nullable=False),
        Column("provenance", String, nullable=False),
        _json_document("input_json"),
        _json_document("preview_json"),
        CheckConstraint(
            "policy_template_id = 'RP-POLICY-FLOW-001'",
            name="return_flow_policy_revision_template",
        ),
        CheckConstraint("revision_number > 0", name="flow_revision_number_positive"),
        CheckConstraint("provenance = 'MANUAL'", name="flow_revision_provenance"),
        UniqueConstraint(
            "policy_template_id",
            "revision_number",
            name="flow_revision_template_number",
        ),
    )
    op.create_index(
        "return_flow_policy_revisions_latest",
        "return_flow_policy_revisions",
        ["policy_template_id", "revision_number"],
    )
    op.create_table(
        "projects",
        Column("project_id", String, primary_key=True),
        Column("name", String, nullable=False),
        Column("acceptance_authority_principal_id", String, nullable=False),
        _json_document(),
        CheckConstraint("length(name) > 0", name="project_name_nonempty"),
    )
    op.create_table(
        "interview_sessions",
        Column("session_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("initiated_at", String, nullable=False),
        _json_document(),
    )
    op.create_table(
        "candidate_facts",
        Column("candidate_fact_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("session_id", String, ForeignKey("interview_sessions.session_id"), nullable=False),
        Column("proposed_at", String, nullable=False),
        _json_document(),
    )
    op.create_table(
        "candidate_decisions",
        Column("decision_id", String, primary_key=True),
        Column(
            "candidate_fact_id",
            String,
            ForeignKey("candidate_facts.candidate_fact_id"),
            nullable=False,
            unique=True,
        ),
        Column("decision_kind", String, nullable=False),
        Column("resulting_domain_event_id", String, unique=True),
        Column("decided_at", String, nullable=False),
        _json_document(),
        CheckConstraint(
            "decision_kind IN ('accepted', 'rejected')",
            name="candidate_decision_kind",
        ),
        CheckConstraint(
            "(decision_kind = 'accepted' AND resulting_domain_event_id IS NOT NULL) OR "
            "(decision_kind = 'rejected' AND resulting_domain_event_id IS NULL)",
            name="candidate_decision_event_shape",
        ),
    )
    op.create_table(
        "project_domain_events",
        Column("event_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("sequence", Integer, nullable=False),
        Column(
            "candidate_fact_id",
            String,
            ForeignKey("candidate_facts.candidate_fact_id"),
            nullable=False,
            unique=True,
        ),
        Column(
            "decision_id",
            String,
            ForeignKey("candidate_decisions.decision_id"),
            nullable=False,
            unique=True,
        ),
        Column("occurred_at", String, nullable=False),
        _json_document(),
        CheckConstraint("sequence > 0", name="project_event_sequence_positive"),
        UniqueConstraint("project_id", "sequence", name="project_event_sequence"),
    )
    op.create_index(
        "project_domain_events_replay",
        "project_domain_events",
        ["project_id", "sequence"],
    )
    op.create_table(
        "project_trust_events",
        Column("trust_event_id", String, primary_key=True),
        Column("project_id", String, ForeignKey("projects.project_id"), nullable=False),
        Column("sequence", Integer, nullable=False),
        Column("event_type", String, nullable=False),
        Column("scope_kind", String, nullable=False),
        Column("scope_id", String, nullable=False),
        Column(
            "linked_revocation_id",
            String,
            ForeignKey("project_trust_events.trust_event_id"),
            unique=True,
        ),
        Column("occurred_at", String, nullable=False),
        _json_document(),
        CheckConstraint("sequence > 0", name="trust_event_sequence_positive"),
        CheckConstraint("event_type IN ('revoked', 'restored')", name="trust_event_type"),
        CheckConstraint("scope_kind IN ('evidence', 'subsystem')", name="trust_scope_kind"),
        CheckConstraint(
            "(event_type = 'revoked' AND linked_revocation_id IS NULL) OR "
            "(event_type = 'restored' AND linked_revocation_id IS NOT NULL)",
            name="trust_event_link_shape",
        ),
        UniqueConstraint(
            "project_id",
            "sequence",
            name="project_trust_event_sequence",
        ),
    )
    op.create_index(
        "project_trust_events_replay",
        "project_trust_events",
        ["project_id", "sequence"],
    )
    op.create_index(
        "project_trust_events_scope",
        "project_trust_events",
        ["project_id", "scope_kind", "scope_id"],
    )
    op.create_table(
        "operator_sessions",
        Column("session_id", String, primary_key=True),
        Column("project_id", String, nullable=False),
        Column("principal_id", String, nullable=False),
        Column("issued_at", Integer, nullable=False),
        Column("authentication_generation", Integer, nullable=False),
        Column("revoked_at", String),
        CheckConstraint("issued_at >= 0", name="operator_session_issued_nonnegative"),
        CheckConstraint(
            "authentication_generation >= 0",
            name="operator_session_generation_nonnegative",
        ),
    )
    op.create_index(
        "operator_sessions_active_lookup",
        "operator_sessions",
        ["project_id", "principal_id", "authentication_generation", "issued_at"],
    )
    op.execute(
        """
        CREATE TRIGGER operator_sessions_no_delete
        BEFORE DELETE ON operator_sessions
        BEGIN
            SELECT RAISE(ABORT, 'operator sessions are immutable except one-time revocation');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER operator_sessions_update_guard
        BEFORE UPDATE ON operator_sessions
        BEGIN
            SELECT CASE
                WHEN NEW.session_id != OLD.session_id
                  OR NEW.project_id != OLD.project_id
                  OR NEW.principal_id != OLD.principal_id
                  OR NEW.issued_at != OLD.issued_at
                  OR NEW.authentication_generation != OLD.authentication_generation
                  OR OLD.revoked_at IS NOT NULL
                  OR NEW.revoked_at IS NULL
                THEN RAISE(ABORT, 'operator sessions are immutable except one-time revocation')
            END;
        END
        """
    )
    op.create_table(
        "api_mutation_audit",
        Column("audit_id", String, primary_key=True),
        Column("request_id", String, nullable=False),
        Column("occurred_at", String, nullable=False),
        Column("route_name", String, nullable=False),
        Column("method", String, nullable=False),
        Column("principal_id", String, nullable=False),
        Column("target_type", String),
        Column("target_id", String),
        Column("outcome", String, nullable=False),
        Column("status_code", Integer, nullable=False),
        CheckConstraint("method IN ('POST', 'PUT', 'PATCH', 'DELETE')", name="api_audit_method"),
        CheckConstraint("status_code >= 100 AND status_code <= 599", name="api_audit_status"),
    )
    for table in _IMMUTABLE_TABLES:
        _immutable(table)


def downgrade() -> None:
    for table in reversed(_IMMUTABLE_TABLES):
        op.drop_table(table)
    op.execute("DROP TRIGGER operator_sessions_update_guard")
    op.execute("DROP TRIGGER operator_sessions_no_delete")
    op.drop_table("operator_sessions")
    op.drop_table("alert_attempts")
    op.drop_table("finding_transitions")
    op.drop_table("active_findings")
    op.drop_table("invariant_results")
    op.drop_table("evaluation_runs")
    op.drop_table("configuration_snapshots")
