"""Persistence evidence for ADR 0003's complete authority chain."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reefproof.project_state import (
    PROJECT_ID,
    AcceptedFactRecord,
    Actor,
    ActorRole,
    CandidateDecision,
    CandidateDecisionKind,
    CandidateFact,
    CandidateValidation,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Project,
    decide_candidate,
)
from reefproof.project_store import ProjectStore
from reefproof.storage import DATABASE_SCHEMA_VERSION, Database

NOW = datetime(2026, 7, 25, 20, 0, tzinfo=UTC)


def _project() -> Project:
    return Project(acceptance_authority_principal_id="acceptance-authority", created_at=NOW)


def _session() -> InterviewSession:
    question = InterviewQuestion(
        question_id="question-return-pump-model",
        prompt="Which return pump model is installed?",
        reason_codes=("MISSING_EQUIPMENT_MODEL",),
        affected_subject_ids=("return_pump",),
    )
    answer = InterviewAnswer(
        answer_id="answer-return-pump-model",
        question_id=question.question_id,
        answered_by_actor_id="acceptance-authority",
        answered_at=NOW,
        source_statement="The label says Varios-8.",
        evidence_ids=("evidence-pump-label",),
    )
    return InterviewSession(
        session_id="session-commissioning",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=NOW,
        purpose="Resolve commissioning unknowns",
        scope_subject_ids=("return_pump",),
        questions=(question,),
        answers=(answer,),
        transcript_evidence_id="evidence-interview",
    )


def _candidate(identifier: str = "return-pump-model") -> CandidateFact:
    return CandidateFact(
        candidate_fact_id=f"candidate-{identifier}",
        project_id=PROJECT_ID,
        subject_id="return_pump",
        attribute=f"equipment.{identifier}",
        proposed_value="Varios-8",
        proposed_by_actor_id="reefproof-agent",
        proposed_at=NOW,
        source_answer_id="answer-return-pump-model",
        evidence_ids=("evidence-pump-label",),
    )


def _validation(candidate: CandidateFact) -> CandidateValidation:
    return CandidateValidation(
        candidate_fact_id=candidate.candidate_fact_id,
        schema_valid=True,
        domain_valid=True,
        reason_codes=(),
        validated_at=NOW,
    )


def _accepted(
    candidate: CandidateFact,
    *,
    suffix: str = "return-pump-model",
    sequence: int = 1,
) -> AcceptedFactRecord:
    decision, event = decide_candidate(
        project=_project(),
        candidate=candidate,
        validation=_validation(candidate),
        deciding_actor=Actor(
            actor_id="acceptance-authority",
            display_name="Legacy authority",
            role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
        ),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id=f"decision-{suffix}",
        decided_at=NOW + timedelta(seconds=sequence),
        rationale="Confirmed from the equipment label.",
        next_event_id=f"event-{suffix}",
        next_sequence=sequence,
    )
    assert event is not None
    return AcceptedFactRecord(candidate=candidate, decision=decision, event=event)


def _store(path: Path) -> ProjectStore:
    database = Database(path)
    database.migrate()
    assert database.schema_version() == DATABASE_SCHEMA_VERSION
    store = ProjectStore(path)
    store.record_project(_project())
    store.record_session(_session())
    return store


def test_release_baseline_creates_project_state_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reefproof.sqlite3"
    Database(path).migrate("head")

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert Database(path).schema_version() == DATABASE_SCHEMA_VERSION
    assert {
        "projects",
        "interview_sessions",
        "candidate_facts",
        "candidate_decisions",
        "project_domain_events",
    } <= tables


def test_candidate_and_rejection_persist_without_canonical_events(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "reefproof.sqlite3")
    proposed = _candidate()
    store.record_candidate(_session().session_id, proposed)
    assert store.load_session(_session().session_id).candidate_facts == (proposed,)
    assert store.replay(PROJECT_ID).facts == ()

    rejection_candidate = _candidate("return-pump-serial")
    rejection = CandidateDecision(
        decision_id="decision-reject-serial",
        candidate_fact_id=rejection_candidate.candidate_fact_id,
        decision=CandidateDecisionKind.REJECTED,
        decided_by_actor_id="acceptance-authority",
        decided_at=NOW,
        validation=_validation(rejection_candidate),
        rationale="The supplied image does not show a serial number.",
    )
    store.record_rejection(_session().session_id, rejection_candidate, rejection)

    reopened = ProjectStore(store.path)
    session = reopened.load_session(_session().session_id)
    assert session.decisions == (rejection,)
    assert len(session.candidate_facts) == 2
    assert reopened.accepted_fact_records(PROJECT_ID) == ()
    assert reopened.replay(PROJECT_ID).facts == ()


def test_complete_acceptance_reloads_and_replays_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    store = _store(path)
    record = _accepted(_candidate())
    store.record_accepted_fact(_session().session_id, record)

    reopened = ProjectStore(path)
    assert reopened.load_project(PROJECT_ID) == _project()
    assert reopened.accepted_fact_records(PROJECT_ID) == (record,)
    state = reopened.replay(PROJECT_ID)
    assert state.last_sequence == 1
    assert state.applied_event_ids == ("event-return-pump-model",)
    fact = state.fact("return_pump", "equipment.return-pump-model")
    assert fact is not None
    assert fact.value == "Varios-8"
    assert fact.source_candidate_fact_id == record.candidate.candidate_fact_id
    assert fact.evidence_ids == ("evidence-pump-label",)


def test_backup_restore_preserves_complete_project_authority_chain(tmp_path: Path) -> None:
    source_path = tmp_path / "source.sqlite3"
    source = _store(source_path)
    record = _accepted(_candidate())
    source.record_accepted_fact(_session().session_id, record)

    inspection = Database(source_path).inspect_evidence()
    assert inspection["counts"] == {
        "snapshots": 0,
        "evaluations": 0,
        "active_findings": 0,
        "finding_transitions": 0,
        "rule_revisions": 0,
        "alert_attempts": 0,
        "projects": 1,
        "sessions": 1,
        "candidate_facts": 1,
        "candidate_decisions": 1,
        "project_domain_events": 1,
        "project_trust_events": 0,
    }

    backup_path = tmp_path / "backup.sqlite3"
    Database(source_path).backup_to(backup_path)
    restored_path = tmp_path / "restored.sqlite3"
    Database.restore_to(backup_path, restored_path)

    restored = ProjectStore(restored_path)
    assert restored.accepted_fact_records(PROJECT_ID) == (record,)
    assert restored.replay(PROJECT_ID) == source.replay(PROJECT_ID)
    assert Database(restored_path).inspect_evidence() == inspection


@pytest.mark.parametrize(
    "table",
    [
        "projects",
        "interview_sessions",
        "candidate_facts",
        "candidate_decisions",
        "project_domain_events",
    ],
)
def test_project_audit_tables_are_sql_append_only(tmp_path: Path, table: str) -> None:
    path = tmp_path / f"{table}.sqlite3"
    store = _store(path)
    store.record_accepted_fact(_session().session_id, _accepted(_candidate()))

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(f"UPDATE {table} SET document_json = '{{}}'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(f"DELETE FROM {table}")


def test_failed_complete_record_rolls_back_candidate_and_decision(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reefproof.sqlite3"
    store = _store(path)
    first = _accepted(_candidate())
    store.record_accepted_fact(_session().session_id, first)
    second_candidate = _candidate("return-pump-power")
    duplicate_event = _accepted(
        second_candidate,
        suffix="return-pump-model",
        sequence=2,
    )

    with pytest.raises(sqlite3.IntegrityError):
        store.record_accepted_fact(_session().session_id, duplicate_event)

    session = store.load_session(_session().session_id)
    assert session.candidate_facts == (first.candidate,)
    assert session.decisions == (first.decision,)
    assert store.accepted_fact_records(PROJECT_ID) == (first,)


def test_replay_rejects_incomplete_tampered_and_out_of_sequence_chains(
    tmp_path: Path,
) -> None:
    incomplete_path = tmp_path / "incomplete.sqlite3"
    incomplete = _store(incomplete_path)
    candidate = _candidate()
    incomplete.record_candidate(_session().session_id, candidate)
    decision = _accepted(candidate).decision
    with sqlite3.connect(incomplete_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO candidate_decisions(
                decision_id, candidate_fact_id, decision_kind,
                resulting_domain_event_id, decided_at, document_json
            ) VALUES (?, ?, 'accepted', ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.candidate_fact_id,
                decision.resulting_domain_event_id,
                decision.decided_at.isoformat(),
                decision.model_dump_json(),
            ),
        )
    with pytest.raises(ValueError, match="incomplete accepted fact chain"):
        incomplete.replay(PROJECT_ID)

    out_of_order_path = tmp_path / "out-of-order.sqlite3"
    out_of_order = _store(out_of_order_path)
    with pytest.raises(ValueError, match="next contiguous"):
        out_of_order.record_accepted_fact(
            _session().session_id,
            _accepted(_candidate(), sequence=2),
        )
    assert out_of_order.load_session(_session().session_id).candidate_facts == ()

    tampered_path = tmp_path / "tampered.sqlite3"
    tampered = _store(tampered_path)
    record = _accepted(_candidate())
    tampered.record_accepted_fact(_session().session_id, record)
    with sqlite3.connect(tampered_path) as connection:
        connection.execute("DROP TRIGGER project_domain_events_no_update")
        connection.execute(
            "UPDATE project_domain_events SET document_json = ? WHERE event_id = ?",
            ('{"event_id":"event-tampered"}', record.event.event_id),
        )
    with pytest.raises(ValueError):
        tampered.replay(PROJECT_ID)


def test_duplicate_sequence_is_rejected_transactionally(tmp_path: Path) -> None:
    store = _store(tmp_path / "reefproof.sqlite3")
    first = _accepted(_candidate())
    store.record_accepted_fact(_session().session_id, first)
    second = _accepted(
        _candidate("return-pump-voltage"),
        suffix="return-pump-voltage",
        sequence=1,
    )

    with pytest.raises(ValueError, match="next contiguous"):
        store.record_accepted_fact(_session().session_id, second)
    assert store.accepted_fact_records(PROJECT_ID) == (first,)


def test_rejection_requires_project_authority(tmp_path: Path) -> None:
    store = _store(tmp_path / "reefproof.sqlite3")
    rejected = _candidate("agent-rejection")
    decision = CandidateDecision(
        decision_id="decision-agent-rejection",
        candidate_fact_id=rejected.candidate_fact_id,
        decision=CandidateDecisionKind.REJECTED,
        decided_by_actor_id="reefproof-agent",
        decided_at=NOW,
        validation=_validation(rejected),
        rationale="An agent cannot reject the acceptance authority's candidate.",
    )

    with pytest.raises(PermissionError, match="lacks acceptance authority"):
        store.record_rejection(_session().session_id, rejected, decision)
    assert store.load_session(_session().session_id).candidate_facts == ()
