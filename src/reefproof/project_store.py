"""SQLite persistence for ADR 0003's append-only project-state records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reefproof.project_state import (
    AcceptedFactRecord,
    CandidateDecision,
    CandidateDecisionKind,
    CandidateFact,
    DomainEvent,
    InterviewSession,
    Project,
    ProjectState,
    replay_project,
)
from reefproof.trust import TrustEvent, TrustRootFact, TrustScopeKind, TrustState, replay_trust


class StoredCandidate(BaseModel):
    """One persisted candidate with its immutable review status."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    session_id: str
    candidate: CandidateFact
    decision: CandidateDecision | None = None


class ProjectStore:
    """Persist complete audit records in an externally migrated SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        uri = f"{self.path.resolve().as_uri()}?mode=rw"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def record_project(self, project: Project) -> None:
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, name, acceptance_authority_principal_id, document_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    project.name,
                    project.acceptance_authority_principal_id,
                    project.model_dump_json(),
                ),
            )

    def list_projects(self) -> tuple[Project, ...]:
        """Return durable projects without changing their recorded identities."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_json FROM projects ORDER BY project_id"
            ).fetchall()
        return tuple(Project.model_validate_json(row["document_json"]) for row in rows)

    def ensure_project(self, project: Project) -> Project:
        """Create the fixed project once or validate the durable identity."""

        with self._connection() as connection, connection:
            row = connection.execute(
                "SELECT document_json FROM projects WHERE project_id = ?",
                (project.project_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO projects(
                        project_id, name, acceptance_authority_principal_id, document_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        project.project_id,
                        project.name,
                        project.acceptance_authority_principal_id,
                        project.model_dump_json(),
                    ),
                )
                return project
            existing = Project.model_validate_json(row["document_json"])
            if (
                existing.name != project.name
                or existing.acceptance_authority_principal_id
                != project.acceptance_authority_principal_id
            ):
                raise ValueError("stored project identity conflicts with the v0.1 project")
            return existing

    def record_session(self, session: InterviewSession) -> None:
        if session.candidate_facts or session.decisions:
            raise ValueError("record the session before its candidate and decision records")
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO interview_sessions(
                    session_id, project_id, initiated_at, document_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.project_id,
                    session.initiated_at.isoformat(),
                    session.model_dump_json(),
                ),
            )

    def record_candidate(self, session_id: str, candidate: CandidateFact) -> None:
        with self._connection() as connection, connection:
            self._insert_candidate(connection, session_id, candidate)

    def record_rejection(
        self,
        session_id: str,
        candidate: CandidateFact,
        decision: CandidateDecision,
    ) -> None:
        """Atomically retain a rejected candidate and decision without an event."""

        if decision.decision is not CandidateDecisionKind.REJECTED:
            raise ValueError("record_rejection requires a rejected decision")
        if decision.candidate_fact_id != candidate.candidate_fact_id:
            raise ValueError("decision and candidate identities do not match")
        with self._connection() as connection, connection:
            project = self._load_project(connection, candidate.project_id)
            if decision.decided_by_actor_id != project.acceptance_authority_principal_id:
                raise PermissionError("candidate rejection lacks acceptance authority")
            self._ensure_candidate(connection, session_id, candidate)
            self._insert_decision(connection, decision)

    def record_rejections(
        self,
        session_id: str,
        records: tuple[tuple[CandidateFact, CandidateDecision], ...],
    ) -> None:
        """Atomically retain a complete rejected import review without events."""

        if not records:
            raise ValueError("bulk rejection requires at least one candidate")
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            project = self._load_project(connection, records[0][0].project_id)
            for candidate, decision in records:
                if decision.decision is not CandidateDecisionKind.REJECTED:
                    raise ValueError("bulk rejection requires rejected decisions")
                if decision.candidate_fact_id != candidate.candidate_fact_id:
                    raise ValueError("decision and candidate identities do not match")
                if decision.decided_by_actor_id != project.acceptance_authority_principal_id:
                    raise PermissionError("candidate rejection lacks acceptance authority")
                self._ensure_candidate(connection, session_id, candidate)
                self._insert_decision(connection, decision)

    def record_accepted_fact(
        self,
        session_id: str,
        record: AcceptedFactRecord,
    ) -> None:
        """Atomically persist the complete candidate-decision-event authority chain."""

        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            project = self._load_project(connection, record.candidate.project_id)
            self._require_project_authority(project, record)
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                FROM project_domain_events
                WHERE project_id = ?
                """,
                (record.event.project_id,),
            ).fetchone()
            assert row is not None
            if record.event.sequence != int(row["next_sequence"]):
                raise ValueError("event sequence must be the next contiguous project sequence")
            self._ensure_candidate(connection, session_id, record.candidate)
            self._insert_decision(connection, record.decision)
            connection.execute(
                """
                INSERT INTO project_domain_events(
                    event_id, project_id, sequence, candidate_fact_id,
                    decision_id, occurred_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event.event_id,
                    record.event.project_id,
                    record.event.sequence,
                    record.event.candidate_fact_id,
                    record.decision.decision_id,
                    record.event.occurred_at.isoformat(),
                    record.event.model_dump_json(),
                ),
            )

    def record_accepted_facts(
        self,
        session_id: str,
        records: tuple[AcceptedFactRecord, ...],
    ) -> None:
        """Atomically persist a prevalidated import-review authority chain."""

        if not records:
            raise ValueError("bulk acceptance requires at least one candidate")
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            project = self._load_project(connection, records[0].candidate.project_id)
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS last_sequence "
                "FROM project_domain_events WHERE project_id = ?",
                (project.project_id,),
            ).fetchone()
            assert row is not None
            expected_sequence = int(row["last_sequence"]) + 1
            for record in records:
                self._require_project_authority(project, record)
                if record.event.sequence != expected_sequence:
                    raise ValueError("bulk event sequences must be contiguous")
                self._ensure_candidate(connection, session_id, record.candidate)
                self._insert_decision(connection, record.decision)
                connection.execute(
                    """
                    INSERT INTO project_domain_events(
                        event_id, project_id, sequence, candidate_fact_id,
                        decision_id, occurred_at, document_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.event.event_id,
                        record.event.project_id,
                        record.event.sequence,
                        record.event.candidate_fact_id,
                        record.decision.decision_id,
                        record.event.occurred_at.isoformat(),
                        record.event.model_dump_json(),
                    ),
                )
                expected_sequence += 1

    def load_project(self, project_id: str) -> Project:
        with self._connection() as connection:
            return self._load_project(connection, project_id)

    def load_session(self, session_id: str) -> InterviewSession:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT document_json FROM interview_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown interview session: {session_id}")
            base = InterviewSession.model_validate_json(row["document_json"])
            candidate_rows = connection.execute(
                """
                SELECT document_json
                FROM candidate_facts
                WHERE session_id = ?
                ORDER BY proposed_at, candidate_fact_id
                """,
                (session_id,),
            ).fetchall()
            candidates = tuple(
                CandidateFact.model_validate_json(candidate["document_json"])
                for candidate in candidate_rows
            )
            if candidates:
                placeholders = ",".join("?" for _ in candidates)
                decision_rows = connection.execute(
                    f"""
                    SELECT document_json
                    FROM candidate_decisions
                    WHERE candidate_fact_id IN ({placeholders})
                    ORDER BY decided_at, decision_id
                    """,
                    tuple(candidate.candidate_fact_id for candidate in candidates),
                ).fetchall()
            else:
                decision_rows = ()
            decisions = tuple(
                CandidateDecision.model_validate_json(decision["document_json"])
                for decision in decision_rows
            )
        return InterviewSession.model_validate(
            {
                **base.model_dump(),
                "candidate_facts": candidates,
                "decisions": decisions,
            }
        )

    def list_sessions(self, project_id: str) -> tuple[InterviewSession, ...]:
        """Load attributable sessions in stable chronological order."""

        with self._connection() as connection:
            self._load_project(connection, project_id)
            rows = connection.execute(
                """
                SELECT session_id
                FROM interview_sessions
                WHERE project_id = ?
                ORDER BY initiated_at, session_id
                """,
                (project_id,),
            ).fetchall()
        return tuple(self.load_session(str(row["session_id"])) for row in rows)

    def load_candidate(self, candidate_fact_id: str) -> StoredCandidate:
        """Load one candidate and its immutable decision, when present."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT c.session_id,
                       c.document_json AS candidate_json,
                       d.document_json AS decision_json
                FROM candidate_facts AS c
                LEFT JOIN candidate_decisions AS d
                  ON d.candidate_fact_id = c.candidate_fact_id
                WHERE c.candidate_fact_id = ?
                """,
                (candidate_fact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown candidate fact: {candidate_fact_id}")
        return StoredCandidate(
            session_id=str(row["session_id"]),
            candidate=CandidateFact.model_validate_json(row["candidate_json"]),
            decision=(
                CandidateDecision.model_validate_json(row["decision_json"])
                if row["decision_json"] is not None
                else None
            ),
        )

    def list_candidates(self, project_id: str) -> tuple[StoredCandidate, ...]:
        """Load candidates in stable proposal order without changing state."""

        with self._connection() as connection:
            self._load_project(connection, project_id)
            rows = connection.execute(
                """
                SELECT candidate_fact_id
                FROM candidate_facts
                WHERE project_id = ?
                ORDER BY proposed_at, candidate_fact_id
                """,
                (project_id,),
            ).fetchall()
        return tuple(self.load_candidate(str(row["candidate_fact_id"])) for row in rows)

    def accepted_fact_records(self, project_id: str) -> tuple[AcceptedFactRecord, ...]:
        """Load and validate every accepted authority chain in replay order."""

        with self._connection() as connection:
            project = self._load_project(connection, project_id)
            incomplete = connection.execute(
                """
                SELECT d.decision_id
                FROM candidate_decisions AS d
                JOIN candidate_facts AS c
                  ON c.candidate_fact_id = d.candidate_fact_id
                LEFT JOIN project_domain_events AS e
                  ON e.event_id = d.resulting_domain_event_id
                 AND e.decision_id = d.decision_id
                 AND e.candidate_fact_id = d.candidate_fact_id
                WHERE c.project_id = ?
                  AND d.decision_kind = 'accepted'
                  AND e.event_id IS NULL
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if incomplete is not None:
                raise ValueError(f"incomplete accepted fact chain: {incomplete['decision_id']}")
            rows = connection.execute(
                """
                SELECT c.document_json AS candidate_json,
                       d.document_json AS decision_json,
                       e.document_json AS event_json
                FROM project_domain_events AS e
                JOIN candidate_facts AS c
                  ON c.candidate_fact_id = e.candidate_fact_id
                JOIN candidate_decisions AS d
                  ON d.decision_id = e.decision_id
                 AND d.candidate_fact_id = c.candidate_fact_id
                 AND d.resulting_domain_event_id = e.event_id
                WHERE e.project_id = ?
                ORDER BY e.sequence
                """,
                (project_id,),
            ).fetchall()
        records = tuple(
            AcceptedFactRecord.model_validate(
                {
                    "candidate": CandidateFact.model_validate_json(row["candidate_json"]),
                    "decision": CandidateDecision.model_validate_json(row["decision_json"]),
                    "event": DomainEvent.model_validate_json(row["event_json"]),
                }
            )
            for row in rows
        )
        for record in records:
            self._require_project_authority(project, record)
        return records

    def replay(self, project_id: str) -> ProjectState:
        project = self.load_project(project_id)
        return replay_project(project, self.accepted_fact_records(project_id))

    def trust_events(self, project_id: str) -> tuple[TrustEvent, ...]:
        """Load the independent immutable trust stream in replay order."""

        with self._connection() as connection:
            self._load_project(connection, project_id)
            rows = connection.execute(
                """
                SELECT document_json
                FROM project_trust_events
                WHERE project_id = ?
                ORDER BY sequence
                """,
                (project_id,),
            ).fetchall()
        return tuple(TrustEvent.model_validate_json(row["document_json"]) for row in rows)

    def replay_trust(self, project_id: str) -> TrustState:
        return replay_trust(project_id, self.trust_events(project_id))

    def trust_roots(
        self,
        project_id: str,
        scope_kind: TrustScopeKind,
        scope_id: str,
    ) -> tuple[TrustRootFact, ...]:
        """Resolve a scope only from registered canonical subjects/evidence."""

        roots = tuple(
            TrustRootFact(
                subject_id=fact.subject_id,
                attribute=fact.attribute,
                evidence_ids=fact.evidence_ids,
                source_candidate_fact_id=fact.source_candidate_fact_id,
            )
            for fact in self.replay(project_id).facts
            if (
                (scope_kind is TrustScopeKind.SUBSYSTEM and fact.subject_id == scope_id)
                or (scope_kind is TrustScopeKind.EVIDENCE and scope_id in fact.evidence_ids)
            )
        )
        if not roots:
            raise KeyError(f"unknown {scope_kind.value} scope: {scope_id}")
        return roots

    def append_trust_event(self, event: TrustEvent) -> TrustState:
        """Append exactly one event after validating the resulting stream."""

        existing = self.trust_events(event.project_id)
        replay_trust(event.project_id, (*existing, event))
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO project_trust_events(
                    trust_event_id, project_id, sequence, event_type, scope_kind,
                    scope_id, linked_revocation_id, occurred_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.trust_event_id,
                    event.project_id,
                    event.sequence,
                    event.event_type,
                    event.scope_kind.value,
                    event.scope_id,
                    event.linked_revocation_id,
                    event.occurred_at.isoformat(),
                    event.model_dump_json(),
                ),
            )
        return self.replay_trust(event.project_id)

    def validate_restoration_candidates(
        self,
        revocation: TrustEvent,
        candidate_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require a fresh accepted replacement for every captured root fact."""

        records = {
            record.candidate.candidate_fact_id: record
            for record in self.accepted_fact_records(revocation.project_id)
            if record.candidate.candidate_fact_id in candidate_ids
        }
        if set(records) != set(candidate_ids):
            raise ValueError("replacement candidates must all be accepted")
        matched: dict[tuple[str, str], AcceptedFactRecord] = {}
        for record in records.values():
            if record.event.occurred_at <= revocation.occurred_at:
                raise ValueError("replacement evidence must be accepted after revocation")
            matched[(record.event.subject_id, record.event.attribute)] = record
        required = {(root.subject_id, root.attribute) for root in revocation.affected_roots}
        if not required.issubset(matched):
            raise ValueError("every revoked root fact requires a fresh replacement")
        return tuple(
            sorted(
                {evidence_id for key in required for evidence_id in matched[key].event.evidence_ids}
            )
        )

    @staticmethod
    def _load_project(connection: sqlite3.Connection, project_id: str) -> Project:
        row = connection.execute(
            "SELECT document_json FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown project: {project_id}")
        project = Project.model_validate_json(row["document_json"])
        if project.project_id != project_id:
            raise ValueError("stored project identity does not match its row identity")
        return project

    @staticmethod
    def _insert_candidate(
        connection: sqlite3.Connection,
        session_id: str,
        candidate: CandidateFact,
    ) -> None:
        session = connection.execute(
            "SELECT project_id FROM interview_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            raise KeyError(f"unknown interview session: {session_id}")
        if session["project_id"] != candidate.project_id:
            raise ValueError("candidate and session belong to different projects")
        connection.execute(
            """
            INSERT INTO candidate_facts(
                candidate_fact_id, project_id, session_id, proposed_at, document_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_fact_id,
                candidate.project_id,
                session_id,
                candidate.proposed_at.isoformat(),
                candidate.model_dump_json(),
            ),
        )

    @classmethod
    def _ensure_candidate(
        cls,
        connection: sqlite3.Connection,
        session_id: str,
        candidate: CandidateFact,
    ) -> None:
        row = connection.execute(
            """
            SELECT session_id, document_json
            FROM candidate_facts
            WHERE candidate_fact_id = ?
            """,
            (candidate.candidate_fact_id,),
        ).fetchone()
        if row is None:
            cls._insert_candidate(connection, session_id, candidate)
            return
        existing = CandidateFact.model_validate_json(row["document_json"])
        if str(row["session_id"]) != session_id or existing != candidate:
            raise ValueError("stored candidate does not match the reviewed candidate")

    @staticmethod
    def _insert_decision(
        connection: sqlite3.Connection,
        decision: CandidateDecision,
    ) -> None:
        connection.execute(
            """
            INSERT INTO candidate_decisions(
                decision_id, candidate_fact_id, decision_kind,
                resulting_domain_event_id, decided_at, document_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.candidate_fact_id,
                decision.decision.value,
                decision.resulting_domain_event_id,
                decision.decided_at.isoformat(),
                decision.model_dump_json(),
            ),
        )

    @staticmethod
    def _require_project_authority(
        project: Project,
        record: AcceptedFactRecord,
    ) -> None:
        if (
            record.decision.decided_by_actor_id != project.acceptance_authority_principal_id
            or record.event.actor_id != project.acceptance_authority_principal_id
        ):
            raise PermissionError("accepted fact lacks acceptance authority")
