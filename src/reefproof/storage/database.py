"""SQLite persistence with explicit transactional migrations."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock
from uuid import uuid4

from alembic import command
from alembic.config import Config
from pydantic import BaseModel, ConfigDict

from reefproof.configuration import ConfigurationSnapshot
from reefproof.invariants import EvaluationRun, InvariantResult, InvariantState, Severity
from reefproof.rules import (
    RETURN_FLOW_POLICY_TEMPLATE_ID,
    ReturnFlowPolicyInputs,
    ReturnFlowPolicyPreview,
    ReturnFlowPolicyRevision,
    preview_flow,
)

DATABASE_SCHEMA_VERSION = 6
DATABASE_ALEMBIC_REVISION = "0006"
_V01_SCHEMA_TABLES = frozenset(
    {
        "active_findings",
        "alert_attempts",
        "alembic_version",
        "api_mutation_audit",
        "candidate_decisions",
        "candidate_facts",
        "configuration_snapshots",
        "evaluation_runs",
        "finding_transitions",
        "interview_sessions",
        "invariant_results",
        "operator_sessions",
        "project_domain_events",
        "project_trust_events",
        "projects",
        "return_flow_policy_revisions",
    }
)
V01_SCHEMA_TABLES = _V01_SCHEMA_TABLES | {
    "authored_source_configurations",
    "authored_source_snapshots",
    "authored_import_batches",
    "authored_source_fetch_attempts",
    "external_identity_bindings",
    "commissioning_verifications",
    "failure_mode_dispositions",
}
_SCHEMA_TABLES_BY_REVISION = {
    "0001": _V01_SCHEMA_TABLES,
    "0002": V01_SCHEMA_TABLES
    - {
        "external_identity_bindings",
        "commissioning_verifications",
        "failure_mode_dispositions",
        "authored_source_fetch_attempts",
    },
    "0003": V01_SCHEMA_TABLES
    - {
        "commissioning_verifications",
        "failure_mode_dispositions",
        "authored_source_fetch_attempts",
    },
    "0004": V01_SCHEMA_TABLES - {"authored_source_fetch_attempts"},
    "0005": V01_SCHEMA_TABLES,
    DATABASE_ALEMBIC_REVISION: V01_SCHEMA_TABLES,
}
_FRESH_SCHEMA_LOCK = Lock()
_FRESH_SCHEMA_IMAGE: bytes | None = None


class FindingTransitionKind(StrEnum):
    OPENED = "opened"
    RECOVERED = "recovered"


class AlertAttemptResult(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AlertAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempt_id: str
    invariant_id: str
    adapter: str
    action: str
    attempted_at: datetime
    result: AlertAttemptResult
    duration_seconds: float
    error_category: str | None = None


class OperatorSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    session_id: str
    project_id: str
    principal_id: str
    issued_at: int
    authentication_generation: int
    revoked_at: datetime | None = None


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    evaluation_run_id: str
    evaluated_at: datetime
    policy_hash: str
    result_count: int
    pass_count: int
    fail_count: int
    unknown_count: int
    detail_retained: bool


class RetentionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    cutoff: datetime
    deleted_result_count: int


class ActiveFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant_id: str
    severity: Severity
    state: InvariantState
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    last_alerted: datetime | None
    result: InvariantResult


class FindingTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant_id: str
    kind: FindingTransitionKind
    transition_at: datetime
    first_seen: datetime
    evaluation_run_id: str


class Database:
    """Small explicit SQLite boundary for ReefProof evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        """Open an existing database without creating files or allowing writes."""

        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self, revision: str = "head") -> None:
        initialized = self._assert_compatible_schema()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not initialized:
            self._initialize_fresh_schema(revision)
        elif self.schema_version() != DATABASE_SCHEMA_VERSION:
            self._upgrade_existing_schema(revision)
        self._assert_compatible_schema(require_head=True)
        with self._connection():
            pass

    def _upgrade_existing_schema(self, revision: str) -> None:
        configuration = Config()
        configuration.set_main_option(
            "script_location",
            str(Path(__file__).parent / "migrations"),
        )
        configuration.set_main_option(
            "sqlalchemy.url",
            f"sqlite:///{self.path.resolve().as_posix()}",
        )
        command.upgrade(configuration, revision)

    def _initialize_fresh_schema(self, revision: str) -> None:
        """Create the canonical empty schema once, then clone that immutable image."""

        global _FRESH_SCHEMA_IMAGE
        if revision != "head":
            raise ValueError("fresh v0.1 databases support only the head schema revision")
        with _FRESH_SCHEMA_LOCK:
            if _FRESH_SCHEMA_IMAGE is None:
                configuration = Config()
                configuration.set_main_option(
                    "script_location",
                    str(Path(__file__).parent / "migrations"),
                )
                configuration.set_main_option(
                    "sqlalchemy.url",
                    f"sqlite:///{self.path.resolve().as_posix()}",
                )
                command.upgrade(configuration, revision)
                with sqlite3.connect(self.path) as connection:
                    _FRESH_SCHEMA_IMAGE = connection.serialize()
                return
            with (
                sqlite3.connect(":memory:") as source,
                sqlite3.connect(self.path) as target,
            ):
                source.deserialize(_FRESH_SCHEMA_IMAGE)
                source.backup(target)

    def _assert_compatible_schema(self, *, require_head: bool = False) -> bool:
        """Reject incompatible existing files without modifying their bytes."""

        if not self.path.exists():
            if require_head:
                raise ValueError("fresh v0.1 database initialization did not create a database")
            return False
        try:
            with self._read_connection() as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                if not tables and not require_head:
                    return False
                if "alembic_version" not in tables:
                    revision = None
                else:
                    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
                    revision = None if row is None else str(row[0])
        except sqlite3.DatabaseError as error:
            raise ValueError(
                "incompatible ReefProof database; preserve or move the existing file aside "
                "and start with a new path"
            ) from error
        expected_tables = _SCHEMA_TABLES_BY_REVISION.get(revision or "")
        if (
            expected_tables is None
            or tables != expected_tables
            or (require_head and revision != DATABASE_ALEMBIC_REVISION)
        ):
            raise ValueError(
                f"incompatible ReefProof database; expected supported schema through "
                f"revision {DATABASE_ALEMBIC_REVISION}. "
                "The existing file was not modified. Preserve or move it aside and start "
                "ReefProof with a new database path."
            )
        return True

    def schema_version(self) -> int:
        with self._read_connection() as connection:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if row is None:
            return 0
        return int(str(row["version_num"]))

    def journal_mode(self) -> str:
        with self._read_connection() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def integrity_check(self) -> str:
        """Return SQLite's full integrity result without modifying evidence."""

        with self._read_connection() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row is not None else "unknown"

    def inspect_evidence(self) -> dict[str, object]:
        """Return fixed, read-only projections of every v0.1 evidence category."""

        with self._read_connection() as connection:
            snapshots = connection.execute(
                """
                SELECT snapshot_hash, configuration_hash, annotation_hash, captured_at
                FROM configuration_snapshots
                ORDER BY captured_at, snapshot_hash
                """
            ).fetchall()
            evaluations = connection.execute(
                """
                SELECT evaluation_run_id, evaluated_at, policy_hash,
                       result_count, pass_count, fail_count, unknown_count
                FROM evaluation_runs
                ORDER BY evaluated_at, evaluation_run_id
                """
            ).fetchall()
            active_findings = connection.execute(
                """
                SELECT invariant_id, severity, state, first_seen, last_seen,
                       occurrence_count, last_alerted
                FROM active_findings
                ORDER BY severity, invariant_id
                """
            ).fetchall()
            transitions = connection.execute(
                """
                SELECT transition_id, invariant_id, kind, transition_at,
                       first_seen, evaluation_run_id
                FROM finding_transitions
                ORDER BY transition_id
                """
            ).fetchall()
            alert_attempts = connection.execute(
                """
                SELECT attempt_id, invariant_id, adapter, action, attempted_at,
                       result, duration_seconds, error_category
                FROM alert_attempts
                ORDER BY attempted_at, attempt_id
                """
            ).fetchall()
            projects = connection.execute(
                """
                SELECT project_id, name, acceptance_authority_principal_id
                FROM projects
                ORDER BY project_id
                """
            ).fetchall()
            sessions = connection.execute(
                """
                SELECT session_id, project_id, initiated_at
                FROM interview_sessions
                ORDER BY initiated_at, session_id
                """
            ).fetchall()
            candidates = connection.execute(
                """
                SELECT candidate_fact_id, project_id, session_id, proposed_at
                FROM candidate_facts
                ORDER BY proposed_at, candidate_fact_id
                """
            ).fetchall()
            decisions = connection.execute(
                """
                SELECT decision_id, candidate_fact_id, decision_kind,
                       resulting_domain_event_id, decided_at
                FROM candidate_decisions
                ORDER BY decided_at, decision_id
                """
            ).fetchall()
            project_events = connection.execute(
                """
                SELECT event_id, project_id, sequence, candidate_fact_id,
                       decision_id, occurred_at
                FROM project_domain_events
                ORDER BY project_id, sequence
                """
            ).fetchall()
            trust_events = connection.execute(
                """
                SELECT trust_event_id, project_id, sequence, event_type,
                       scope_kind, scope_id, linked_revocation_id, occurred_at
                FROM project_trust_events
                ORDER BY project_id, sequence
                """
            ).fetchall()
        revisions = self.return_flow_policy_revisions()
        categories: dict[str, object] = {
            "snapshots": [dict(row) for row in snapshots],
            "evaluations": [dict(row) for row in evaluations],
            "findings": {
                "active": [dict(row) for row in active_findings],
                "transitions": [dict(row) for row in transitions],
            },
            "rule_revisions": [revision.model_dump(mode="json") for revision in revisions],
            "alert_attempts": [dict(row) for row in alert_attempts],
            "project_state": {
                "projects": [dict(row) for row in projects],
                "sessions": [dict(row) for row in sessions],
                "candidates": [dict(row) for row in candidates],
                "decisions": [dict(row) for row in decisions],
                "events": [dict(row) for row in project_events],
                "trust_events": [dict(row) for row in trust_events],
            },
        }
        return {
            "schema_version": self.schema_version(),
            "categories": categories,
            "counts": {
                "snapshots": len(snapshots),
                "evaluations": len(evaluations),
                "active_findings": len(active_findings),
                "finding_transitions": len(transitions),
                "rule_revisions": len(revisions),
                "alert_attempts": len(alert_attempts),
                "projects": len(projects),
                "sessions": len(sessions),
                "candidate_facts": len(candidates),
                "candidate_decisions": len(decisions),
                "project_domain_events": len(project_events),
                "project_trust_events": len(trust_events),
            },
        }

    def backup_to(self, destination: Path) -> None:
        """Atomically create one SQLite-consistent backup at a new path."""

        destination = destination.resolve()
        if destination.exists():
            raise FileExistsError(f"backup destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.partial")
        try:
            with (
                self._read_connection() as source,
                sqlite3.connect(temporary) as target,
            ):
                source.backup(target)
            copied = Database(temporary)
            if copied.integrity_check() != "ok":
                raise sqlite3.DatabaseError("backup integrity check failed")
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            for suffix in ("-wal", "-shm"):
                temporary.with_name(f"{temporary.name}{suffix}").unlink(missing_ok=True)

    @classmethod
    def restore_to(cls, source: Path, destination: Path) -> Database:
        """Restore a verified backup to a new explicit destination."""

        source_database = cls(source)
        source_integrity = source_database.integrity_check()
        if source_integrity != "ok":
            raise sqlite3.DatabaseError(f"backup integrity check failed: {source_integrity}")
        source_schema = source_database.schema_version()
        if source_schema != DATABASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported backup schema version: {source_schema}")
        source_latest = source_database.latest_return_flow_policy_revision()
        source_inspection = source_database.inspect_evidence()
        source_database.backup_to(destination)
        restored = cls(destination)
        try:
            if restored.integrity_check() != "ok":
                raise sqlite3.DatabaseError("restored database integrity check failed")
            if restored.schema_version() != source_schema:
                raise ValueError("restored schema does not match the backup")
            if restored.latest_return_flow_policy_revision() != source_latest:
                raise ValueError("restored latest rule revision does not match the backup")
            if restored.inspect_evidence() != source_inspection:
                raise ValueError("restored evidence view does not match the backup")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return restored

    def record_operator_session(
        self,
        *,
        project_id: str,
        session_id: str,
        principal_id: str,
        issued_at: int,
        authentication_generation: int,
    ) -> None:
        session = OperatorSessionRecord(
            session_id=session_id,
            project_id=project_id,
            principal_id=principal_id,
            issued_at=issued_at,
            authentication_generation=authentication_generation,
        )
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO operator_sessions(
                    session_id,
                    project_id,
                    principal_id,
                    issued_at,
                    authentication_generation,
                    revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    session.session_id,
                    session.project_id,
                    session.principal_id,
                    session.issued_at,
                    session.authentication_generation,
                ),
            )

    def record_api_mutation(
        self,
        *,
        request_id: str,
        route_name: str,
        method: str,
        principal_id: str,
        target_type: str | None,
        target_id: str | None,
        outcome: str,
        status_code: int,
        occurred_at: datetime,
    ) -> None:
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO api_mutation_audit(
                    audit_id, request_id, occurred_at, route_name, method,
                    principal_id, target_type, target_id, outcome, status_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    request_id,
                    occurred_at.isoformat(),
                    route_name,
                    method,
                    principal_id,
                    target_type,
                    target_id,
                    outcome,
                    status_code,
                ),
            )

    def api_mutation_audit_count(self, route_name: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM api_mutation_audit"
        parameters: tuple[str, ...] = ()
        if route_name is not None:
            query += " WHERE route_name = ?"
            parameters = (route_name,)
        with self._read_connection() as connection:
            row = connection.execute(query, parameters).fetchone()
        return int(row[0])

    def revoke_operator_session(
        self,
        *,
        project_id: str,
        session_id: str,
        revoked_at: datetime,
    ) -> bool:
        with self._connection() as connection, connection:
            row = connection.execute(
                """
                SELECT principal_id, issued_at, authentication_generation
                FROM operator_sessions
                WHERE project_id = ?
                  AND session_id = ?
                  AND revoked_at IS NULL
                """,
                (project_id, session_id),
            ).fetchone()
            if row is None:
                return False
            revoked_session = OperatorSessionRecord(
                session_id=session_id,
                project_id=project_id,
                principal_id=str(row["principal_id"]),
                issued_at=int(row["issued_at"]),
                authentication_generation=int(row["authentication_generation"]),
                revoked_at=revoked_at,
            )
            validated_revoked_at = revoked_session.revoked_at
            assert validated_revoked_at is not None
            cursor = connection.execute(
                """
                UPDATE operator_sessions
                SET revoked_at = ?
                WHERE project_id = ?
                  AND session_id = ?
                  AND revoked_at IS NULL
                """,
                (
                    validated_revoked_at.isoformat(),
                    project_id,
                    session_id,
                ),
            )
        return cursor.rowcount == 1

    def operator_session_exists(
        self,
        *,
        project_id: str,
        session_id: str,
        principal_id: str,
        authentication_generation: int,
    ) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM operator_sessions
                WHERE project_id = ?
                  AND session_id = ?
                  AND principal_id = ?
                  AND authentication_generation = ?
                  AND revoked_at IS NULL
                """,
                (project_id, session_id, principal_id, authentication_generation),
            ).fetchone()
        return row is not None

    def list_active_operator_sessions(
        self,
        *,
        project_id: str,
        principal_id: str,
        authentication_generation: int,
    ) -> tuple[OperatorSessionRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id,
                       project_id,
                       principal_id,
                       issued_at,
                       authentication_generation,
                       revoked_at
                FROM operator_sessions
                WHERE project_id = ?
                  AND principal_id = ?
                  AND authentication_generation = ?
                  AND revoked_at IS NULL
                ORDER BY issued_at, session_id
                """,
                (project_id, principal_id, authentication_generation),
            ).fetchall()
        return tuple(
            OperatorSessionRecord(
                session_id=str(row["session_id"]),
                project_id=str(row["project_id"]),
                principal_id=str(row["principal_id"]),
                issued_at=int(row["issued_at"]),
                authentication_generation=int(row["authentication_generation"]),
                revoked_at=(
                    datetime.fromisoformat(str(row["revoked_at"]))
                    if row["revoked_at"] is not None
                    else None
                ),
            )
            for row in rows
        )

    def evaluation_exists(self, evaluation_run_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM evaluation_runs WHERE evaluation_run_id = ?",
                (evaluation_run_id,),
            ).fetchone()
        return row is not None

    def record_snapshot(self, snapshot: ConfigurationSnapshot) -> bool:
        document = snapshot.model_dump_json()
        with self._connection() as connection, connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO configuration_snapshots(
                    snapshot_hash,
                    configuration_hash,
                    annotation_hash,
                    captured_at,
                    document_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_hash,
                    snapshot.configuration_hash,
                    snapshot.annotation_hash,
                    snapshot.captured_at.isoformat(),
                    document,
                ),
            )
        return cursor.rowcount == 1

    def snapshot_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM configuration_snapshots"
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def latest_snapshot(self) -> ConfigurationSnapshot | None:
        """Return the newest persisted normalized snapshot, if one exists."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json
                FROM configuration_snapshots
                ORDER BY captured_at DESC, snapshot_hash DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return ConfigurationSnapshot.model_validate_json(str(row["document_json"]))

    def record_return_flow_policy_revision(
        self,
        inputs: ReturnFlowPolicyInputs,
        *,
        created_at: datetime,
        authoring_operator_session_id: str,
    ) -> ReturnFlowPolicyRevision:
        """Append one backend-derived immutable local flow-rule revision."""

        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        preview = preview_flow(inputs)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(revision_number), 0) + 1 AS next_revision
                    FROM return_flow_policy_revisions
                    WHERE policy_template_id = ?
                    """,
                    (RETURN_FLOW_POLICY_TEMPLATE_ID,),
                ).fetchone()
                revision_number = int(row["next_revision"]) if row is not None else 1
                revision = ReturnFlowPolicyRevision(
                    revision_id=str(uuid4()),
                    revision_number=revision_number,
                    created_at=created_at,
                    authoring_operator_session_id=authoring_operator_session_id,
                    inputs=inputs,
                    preview=preview,
                )
                connection.execute(
                    """
                    INSERT INTO return_flow_policy_revisions(
                        revision_id,
                        policy_template_id,
                        revision_number,
                        created_at,
                        authoring_operator_session_id,
                        provenance,
                        input_json,
                        preview_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        revision.revision_id,
                        revision.policy_template_id,
                        revision.revision_number,
                        revision.created_at.isoformat(),
                        revision.authoring_operator_session_id,
                        revision.provenance,
                        revision.inputs.model_dump_json(),
                        revision.preview.model_dump_json(),
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return revision

    def latest_return_flow_policy_revision(self) -> ReturnFlowPolicyRevision | None:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM return_flow_policy_revisions
                WHERE policy_template_id = ?
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (RETURN_FLOW_POLICY_TEMPLATE_ID,),
            ).fetchone()
        return None if row is None else self._return_flow_policy_revision_from_row(row)

    def return_flow_policy_revisions(self) -> tuple[ReturnFlowPolicyRevision, ...]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM return_flow_policy_revisions
                WHERE policy_template_id = ?
                ORDER BY revision_number
                """,
                (RETURN_FLOW_POLICY_TEMPLATE_ID,),
            ).fetchall()
        return tuple(self._return_flow_policy_revision_from_row(row) for row in rows)

    @staticmethod
    def _return_flow_policy_revision_from_row(row: sqlite3.Row) -> ReturnFlowPolicyRevision:
        inputs = ReturnFlowPolicyInputs.model_validate_json(str(row["input_json"]))
        return ReturnFlowPolicyRevision.model_validate(
            {
                "revision_id": str(row["revision_id"]),
                "policy_template_id": str(row["policy_template_id"]),
                "revision_number": int(row["revision_number"]),
                "created_at": datetime.fromisoformat(str(row["created_at"])),
                "authoring_operator_session_id": str(row["authoring_operator_session_id"]),
                "provenance": str(row["provenance"]),
                "inputs": inputs,
                "preview": ReturnFlowPolicyPreview.model_validate_json(str(row["preview_json"])),
            }
        )

    def record_evaluation(
        self,
        run: EvaluationRun,
    ) -> tuple[FindingTransition, ...]:
        for result in run.results:
            if result.evaluation_run_id != run.evaluation_run_id:
                raise ValueError("result evaluation_run_id does not match its run")

        transitions: list[FindingTransition] = []
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO evaluation_runs(
                        evaluation_run_id,
                        evaluated_at,
                        policy_hash,
                        result_count,
                        pass_count,
                        fail_count,
                        unknown_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.evaluation_run_id,
                        run.evaluation_timestamp.isoformat(),
                        run.policy_hash,
                        len(run.results),
                        sum(result.state is InvariantState.PASS for result in run.results),
                        sum(result.state is InvariantState.FAIL for result in run.results),
                        sum(result.state is InvariantState.UNKNOWN for result in run.results),
                    ),
                )
                for result_index, result in enumerate(run.results):
                    self._insert_result(connection, result, result_index)
                    transition = self._apply_finding_result(connection, result)
                    if transition is not None:
                        transitions.append(transition)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return tuple(transitions)

    @staticmethod
    def _insert_result(
        connection: sqlite3.Connection,
        result: InvariantResult,
        result_index: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO invariant_results(
                evaluation_run_id,
                invariant_id,
                result_index,
                state,
                severity,
                document_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result.evaluation_run_id,
                result.invariant_id,
                result_index,
                result.state.value,
                result.severity.value,
                result.model_dump_json(),
            ),
        )

    @staticmethod
    def _apply_finding_result(
        connection: sqlite3.Connection,
        result: InvariantResult,
    ) -> FindingTransition | None:
        existing = connection.execute(
            "SELECT invariant_id, first_seen FROM active_findings WHERE invariant_id = ?",
            (result.invariant_id,),
        ).fetchone()
        timestamp = result.evaluation_timestamp.isoformat()
        if result.state is InvariantState.PASS:
            if existing is None:
                return None
            connection.execute(
                "DELETE FROM active_findings WHERE invariant_id = ?",
                (result.invariant_id,),
            )
            transition = FindingTransition(
                invariant_id=result.invariant_id,
                kind=FindingTransitionKind.RECOVERED,
                transition_at=result.evaluation_timestamp,
                first_seen=datetime.fromisoformat(str(existing["first_seen"])),
                evaluation_run_id=result.evaluation_run_id,
            )
            Database._insert_transition(connection, transition, result)
            return transition

        if existing is not None:
            connection.execute(
                """
                UPDATE active_findings
                SET severity = ?,
                    state = ?,
                    last_seen = ?,
                    occurrence_count = occurrence_count + 1,
                    result_json = ?
                WHERE invariant_id = ?
                """,
                (
                    result.severity.value,
                    result.state.value,
                    timestamp,
                    result.model_dump_json(),
                    result.invariant_id,
                ),
            )
            return None

        connection.execute(
            """
            INSERT INTO active_findings(
                invariant_id,
                severity,
                state,
                first_seen,
                last_seen,
                occurrence_count,
                last_alerted,
                result_json
            ) VALUES (?, ?, ?, ?, ?, 1, NULL, ?)
            """,
            (
                result.invariant_id,
                result.severity.value,
                result.state.value,
                timestamp,
                timestamp,
                result.model_dump_json(),
            ),
        )
        transition = FindingTransition(
            invariant_id=result.invariant_id,
            kind=FindingTransitionKind.OPENED,
            transition_at=result.evaluation_timestamp,
            first_seen=result.evaluation_timestamp,
            evaluation_run_id=result.evaluation_run_id,
        )
        Database._insert_transition(connection, transition, result)
        return transition

    @staticmethod
    def _insert_transition(
        connection: sqlite3.Connection,
        transition: FindingTransition,
        result: InvariantResult,
    ) -> None:
        connection.execute(
            """
            INSERT INTO finding_transitions(
                invariant_id,
                kind,
                transition_at,
                first_seen,
                evaluation_run_id,
                result_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transition.invariant_id,
                transition.kind.value,
                transition.transition_at.isoformat(),
                transition.first_seen.isoformat(),
                transition.evaluation_run_id,
                result.model_dump_json(),
            ),
        )

    def active_finding(self, invariant_id: str) -> ActiveFinding | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM active_findings WHERE invariant_id = ?",
                (invariant_id,),
            ).fetchone()
        if row is None:
            return None
        return self._active_finding_from_row(row)

    def active_findings(self) -> tuple[ActiveFinding, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM active_findings ORDER BY invariant_id"
            ).fetchall()
        return tuple(self._active_finding_from_row(row) for row in rows)

    @staticmethod
    def _active_finding_from_row(row: sqlite3.Row) -> ActiveFinding:
        return ActiveFinding(
            invariant_id=str(row["invariant_id"]),
            severity=Severity(str(row["severity"])),
            state=InvariantState(str(row["state"])),
            first_seen=datetime.fromisoformat(str(row["first_seen"])),
            last_seen=datetime.fromisoformat(str(row["last_seen"])),
            occurrence_count=int(row["occurrence_count"]),
            last_alerted=(
                datetime.fromisoformat(str(row["last_alerted"]))
                if row["last_alerted"] is not None
                else None
            ),
            result=InvariantResult.model_validate_json(str(row["result_json"])),
        )

    def active_finding_counts(self) -> dict[tuple[Severity, InvariantState], int]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT severity, state, COUNT(*) AS count
                FROM active_findings
                GROUP BY severity, state
                ORDER BY severity, state
                """
            ).fetchall()
        return {
            (Severity(str(row["severity"])), InvariantState(str(row["state"]))): int(row["count"])
            for row in rows
        }

    def transition_count(self, invariant_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM finding_transitions
                WHERE invariant_id = ?
                """,
                (invariant_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def evaluation_results(self, evaluation_run_id: str) -> tuple[InvariantResult, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT document_json
                FROM invariant_results
                WHERE evaluation_run_id = ?
                ORDER BY result_index
                """,
                (evaluation_run_id,),
            ).fetchall()
        return tuple(InvariantResult.model_validate_json(str(row["document_json"])) for row in rows)

    def evaluation_run_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM evaluation_runs").fetchone()
        return int(row["count"]) if row is not None else 0

    def evaluation_summary(self, evaluation_run_id: str) -> EvaluationSummary:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT evaluation_run_id,
                       evaluated_at,
                       policy_hash,
                       result_count,
                       pass_count,
                       fail_count,
                       unknown_count,
                       EXISTS(
                           SELECT 1
                           FROM invariant_results
                           WHERE invariant_results.evaluation_run_id =
                                 evaluation_runs.evaluation_run_id
                       ) AS detail_retained
                FROM evaluation_runs
                WHERE evaluation_run_id = ?
                """,
                (evaluation_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown evaluation run: {evaluation_run_id}")
        return EvaluationSummary(
            evaluation_run_id=str(row["evaluation_run_id"]),
            evaluated_at=datetime.fromisoformat(str(row["evaluated_at"])),
            policy_hash=str(row["policy_hash"]),
            result_count=int(row["result_count"]),
            pass_count=int(row["pass_count"]),
            fail_count=int(row["fail_count"]),
            unknown_count=int(row["unknown_count"]),
            detail_retained=bool(row["detail_retained"]),
        )

    def prune_evaluation_details(self, *, before: datetime) -> RetentionReport:
        """Delete only invariant-result detail strictly older than the cutoff."""

        if before.tzinfo is None or before.utcoffset() is None:
            raise ValueError("retention cutoff must include a timezone")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    """
                    DELETE FROM invariant_results
                    WHERE evaluation_run_id IN (
                        SELECT evaluation_run_id
                        FROM evaluation_runs
                        WHERE julianday(evaluated_at) < julianday(?)
                    )
                    """,
                    (before.isoformat(),),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return RetentionReport(
            cutoff=before,
            deleted_result_count=cursor.rowcount,
        )

    def invariant_result_counts(
        self,
    ) -> dict[tuple[InvariantState, Severity, str], int]:
        """Aggregate durable results without hashes or entity identifiers."""

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT state, severity, invariant_id, COUNT(*) AS count
                FROM invariant_results
                GROUP BY state, severity, invariant_id
                ORDER BY invariant_id, severity, state
                """
            ).fetchall()
        return {
            (
                InvariantState(str(row["state"])),
                Severity(str(row["severity"])),
                str(row["invariant_id"]),
            ): int(row["count"])
            for row in rows
        }

    def record_alert_attempt(self, attempt: AlertAttempt) -> None:
        if attempt.attempted_at.tzinfo is None or attempt.attempted_at.utcoffset() is None:
            raise ValueError("attempted_at must include a timezone")
        if attempt.duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO alert_attempts(
                        attempt_id,
                        invariant_id,
                        adapter,
                        action,
                        attempted_at,
                        result,
                        duration_seconds,
                        error_category
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt.attempt_id,
                        attempt.invariant_id,
                        attempt.adapter,
                        attempt.action,
                        attempt.attempted_at.isoformat(),
                        attempt.result.value,
                        attempt.duration_seconds,
                        attempt.error_category,
                    ),
                )
                if attempt.result is AlertAttemptResult.SUCCESS:
                    connection.execute(
                        """
                        UPDATE active_findings
                        SET last_alerted = ?
                        WHERE invariant_id = ?
                        """,
                        (attempt.attempted_at.isoformat(), attempt.invariant_id),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def alert_attempt_count(self, invariant_id: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM alert_attempts
                WHERE invariant_id = ?
                """,
                (invariant_id,),
            ).fetchone()
        return int(row["count"]) if row is not None else 0

    def last_successful_alert_at(
        self,
        invariant_id: str,
        adapter: str,
    ) -> datetime | None:
        """Return adapter-specific delivery state for independent retries."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT MAX(attempted_at) AS last_success
                FROM alert_attempts
                WHERE invariant_id = ?
                  AND adapter = ?
                  AND result = ?
                """,
                (
                    invariant_id,
                    adapter,
                    AlertAttemptResult.SUCCESS.value,
                ),
            ).fetchone()
        if row is None or row["last_success"] is None:
            return None
        return datetime.fromisoformat(str(row["last_success"]))

    def alert_attempt_metrics(
        self,
    ) -> dict[tuple[str, AlertAttemptResult], tuple[int, float]]:
        """Aggregate bounded alert outcomes and their mean duration."""

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT adapter,
                       result,
                       COUNT(*) AS count,
                       AVG(duration_seconds) AS mean_duration
                FROM alert_attempts
                GROUP BY adapter, result
                ORDER BY adapter, result
                """
            ).fetchall()
        return {
            (
                str(row["adapter"]),
                AlertAttemptResult(str(row["result"])),
            ): (
                int(row["count"]),
                float(row["mean_duration"]),
            )
            for row in rows
        }
