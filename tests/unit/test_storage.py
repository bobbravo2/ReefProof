from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from reefproof.configuration import load_fixture, snapshot_fixture
from reefproof.invariants import EvaluationRun, InvariantState, Severity, evaluate_graph
from reefproof.reliability import build_graph
from reefproof.rules import ReturnFlowPolicyInputs
from reefproof.storage import (
    DATABASE_SCHEMA_VERSION,
    AlertAttempt,
    AlertAttemptResult,
    Database,
    FindingTransitionKind,
)

AUTHOR_SESSION_ID = "12345678-abcd-4234-8234-123456789abc"

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T19:00:00-04:00")


def _evaluation(run_id: str = "e2345678-1234-4234-8234-123456789abc") -> EvaluationRun:
    snapshot = snapshot_fixture(load_fixture(FIXTURE))
    return evaluate_graph(
        build_graph(snapshot),
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=run_id,
    )


def _recovery(run: EvaluationRun) -> EvaluationRun:
    failing = next(result for result in run.results if result.invariant_id == "RP-CIRC-001")
    passing = failing.model_copy(
        update={
            "state": InvariantState.PASS,
            "summary": "Returns are independent.",
            "detailed_explanation": "The unsafe correlation was removed.",
            "missing_evidence": (),
            "evaluation_run_id": "f2345678-1234-4234-8234-123456789abc",
        }
    )
    return EvaluationRun(
        evaluation_run_id=passing.evaluation_run_id,
        evaluation_timestamp=TIMESTAMP,
        policy_hash=run.policy_hash,
        results=(passing,),
    )


def test_database_migrates_and_uses_wal(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()

    assert database.schema_version() == DATABASE_SCHEMA_VERSION
    assert database.journal_mode() == "wal"

    with sqlite3.connect(database.path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(operator_sessions)")
        }
    assert "document_json" not in columns


def test_operator_sessions_are_persisted_listed_and_revoked(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()

    database.record_operator_session(
        project_id="primary-reef-system",
        session_id="11111111-1111-4111-8111-111111111111",
        principal_id="local-acceptance-authority",
        issued_at=100,
        authentication_generation=0,
    )
    database.record_operator_session(
        project_id="primary-reef-system",
        session_id="22222222-2222-4222-8222-222222222222",
        principal_id="local-acceptance-authority",
        issued_at=101,
        authentication_generation=0,
    )

    listed = database.list_active_operator_sessions(
        project_id="primary-reef-system",
        principal_id="local-acceptance-authority",
        authentication_generation=0,
    )
    assert tuple(row.session_id for row in listed) == (
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
    )
    assert database.operator_session_exists(
        project_id="primary-reef-system",
        session_id="11111111-1111-4111-8111-111111111111",
        principal_id="local-acceptance-authority",
        authentication_generation=0,
    )

    revoked = database.revoke_operator_session(
        project_id="primary-reef-system",
        session_id="11111111-1111-4111-8111-111111111111",
        revoked_at=TIMESTAMP,
    )
    assert revoked is True
    assert (
        database.operator_session_exists(
            project_id="primary-reef-system",
            session_id="11111111-1111-4111-8111-111111111111",
            principal_id="local-acceptance-authority",
            authentication_generation=0,
        )
        is False
    )

    remaining = database.list_active_operator_sessions(
        project_id="primary-reef-system",
        principal_id="local-acceptance-authority",
        authentication_generation=0,
    )
    assert tuple(row.session_id for row in remaining) == ("22222222-2222-4222-8222-222222222222",)


def test_release_schema_rejects_invalid_json_and_unbalanced_summary(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()

    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO configuration_snapshots(
                snapshot_hash, configuration_hash, annotation_hash, captured_at, document_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "sha256:" + "1" * 64,
                "sha256:" + "2" * 64,
                "sha256:" + "3" * 64,
                TIMESTAMP.isoformat(),
                "not-json",
            ),
        )

    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO evaluation_runs(
                evaluation_run_id, evaluated_at, policy_hash,
                result_count, pass_count, fail_count, unknown_count
            ) VALUES (?, ?, ?, 2, 1, 0, 0)
            """,
            ("release-contract", TIMESTAMP.isoformat(), "sha256:" + "4" * 64),
        )


def test_release_schema_fails_closed_on_old_development_revision(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE alembic_version(version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0008')")
        connection.execute("CREATE TABLE preserved_marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO preserved_marker VALUES ('keep')")

    before = path.read_bytes()
    with pytest.raises(ValueError, match="incompatible ReefProof database"):
        Database(path).migrate()

    assert path.read_bytes() == before

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM preserved_marker").fetchone() == ("keep",)


def test_distinct_snapshot_is_not_duplicated(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    snapshot = snapshot_fixture(load_fixture(FIXTURE))

    assert database.record_snapshot(snapshot) is True
    assert database.record_snapshot(snapshot) is False
    assert database.snapshot_count() == 1


def test_return_flow_policy_revisions_are_append_only_and_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()
    first_inputs = ReturnFlowPolicyInputs(
        tank_volume_gallons=250,
        pump_rated_flow_gph=800,
        delivered_flow_gph=650,
        minimum_turnover_per_hour=2,
    )
    second_inputs = first_inputs.model_copy(update={"delivered_flow_gph": 500})

    first = database.record_return_flow_policy_revision(
        first_inputs,
        created_at=TIMESTAMP,
        authoring_operator_session_id=AUTHOR_SESSION_ID,
    )
    second = database.record_return_flow_policy_revision(
        second_inputs,
        created_at=TIMESTAMP + timedelta(minutes=1),
        authoring_operator_session_id=AUTHOR_SESSION_ID,
    )

    assert first.revision_number == 1
    assert first.preview.state == "PASS"
    assert second.revision_number == 2
    assert second.preview.state == "PASS"
    assert second.preview.actual_turnover_per_hour == 2

    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute(
            "UPDATE return_flow_policy_revisions SET revision_number = 99 WHERE revision_id = ?",
            (first.revision_id,),
        )
    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute(
            "DELETE FROM return_flow_policy_revisions WHERE revision_id = ?",
            (first.revision_id,),
        )

    restarted = Database(path)
    assert restarted.return_flow_policy_revisions() == (first, second)
    assert restarted.latest_return_flow_policy_revision() == second


def test_return_flow_policy_revision_rejects_naive_creation_time(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()

    with pytest.raises(ValueError, match="timezone"):
        database.record_return_flow_policy_revision(
            ReturnFlowPolicyInputs(
                tank_volume_gallons=250,
                pump_rated_flow_gph=800,
                delivered_flow_gph=650,
                minimum_turnover_per_hour=2,
            ),
            created_at=datetime(2026, 7, 25),
            authoring_operator_session_id=AUTHOR_SESSION_ID,
        )


def test_repeated_finding_is_deduplicated_and_counted(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    first_run = _evaluation()
    second_run = _evaluation("12345678-2234-4234-8234-123456789abc")

    first_transitions = database.record_evaluation(first_run)
    second_transitions = database.record_evaluation(second_run)
    finding = database.active_finding("RP-CIRC-001")

    assert any(
        transition.invariant_id == "RP-CIRC-001" and transition.kind is FindingTransitionKind.OPENED
        for transition in first_transitions
    )
    assert not any(transition.invariant_id == "RP-CIRC-001" for transition in second_transitions)
    assert finding is not None
    assert finding.occurrence_count == 2
    assert finding.first_seen == TIMESTAMP
    assert finding.last_seen == TIMESTAMP
    stored = database.evaluation_results(first_run.evaluation_run_id)
    assert stored == first_run.results


def test_mismatched_result_rolls_back_the_evaluation(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    run = _evaluation()
    mismatched = run.model_copy(
        update={
            "results": (
                run.results[0].model_copy(
                    update={"evaluation_run_id": "aaaaaaaa-1234-4234-8234-123456789abc"}
                ),
            )
        }
    )

    with pytest.raises(ValueError, match="does not match"):
        database.record_evaluation(mismatched)

    assert database.evaluation_run_count() == 0


def test_recovery_is_recorded_once_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()
    run = _evaluation()
    database.record_evaluation(run)

    restarted = Database(path)
    recovery = _recovery(run)
    first = restarted.record_evaluation(recovery)
    repeated_run_id = "02345678-1234-4234-8234-123456789abc"
    repeated_result = recovery.results[0].model_copy(update={"evaluation_run_id": repeated_run_id})
    second = restarted.record_evaluation(
        recovery.model_copy(
            update={
                "evaluation_run_id": repeated_run_id,
                "results": (repeated_result,),
            }
        )
    )

    assert [
        transition.kind for transition in first if transition.invariant_id == "RP-CIRC-001"
    ] == [FindingTransitionKind.RECOVERED]
    assert not any(transition.invariant_id == "RP-CIRC-001" for transition in second)
    assert restarted.active_finding("RP-CIRC-001") is None
    assert restarted.transition_count("RP-CIRC-001") == 2


def test_only_successful_alert_attempt_advances_last_alerted(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()
    database.record_evaluation(_evaluation())
    failed = AlertAttempt(
        attempt_id="attempt-failed",
        invariant_id="RP-CIRC-001",
        adapter="console",
        action="send_new",
        attempted_at=TIMESTAMP,
        result=AlertAttemptResult.FAILURE,
        duration_seconds=0.01,
        error_category="alert_delivery",
    )
    succeeded = failed.model_copy(
        update={
            "attempt_id": "attempt-succeeded",
            "attempted_at": TIMESTAMP.replace(second=1),
            "result": AlertAttemptResult.SUCCESS,
            "error_category": None,
        }
    )

    database.record_alert_attempt(failed)
    finding_after_failure = database.active_finding("RP-CIRC-001")
    assert finding_after_failure is not None
    assert finding_after_failure.last_alerted is None

    restarted = Database(path)
    restarted.record_alert_attempt(succeeded)

    finding = restarted.active_finding("RP-CIRC-001")
    assert finding is not None
    assert finding.last_alerted == succeeded.attempted_at
    assert restarted.alert_attempt_count("RP-CIRC-001") == 2
    assert restarted.alert_attempt_metrics() == {
        ("console", AlertAttemptResult.FAILURE): (1, 0.01),
        ("console", AlertAttemptResult.SUCCESS): (1, 0.01),
    }


def test_invariant_result_counts_are_grouped_by_bounded_dimensions(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    database.record_evaluation(_evaluation())

    counts = database.invariant_result_counts()

    assert counts[(InvariantState.FAIL, Severity.CRITICAL, "RP-CIRC-001")] == 1


def test_explicit_retention_prunes_only_old_evaluation_detail(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    snapshot = snapshot_fixture(load_fixture(FIXTURE))
    database.record_snapshot(snapshot)
    old = _evaluation()
    recent_time = TIMESTAMP + timedelta(days=10)
    recent_run_id = "d2345678-1234-4234-8234-123456789abc"
    recent = old.model_copy(
        update={
            "evaluation_run_id": recent_run_id,
            "evaluation_timestamp": recent_time,
            "results": tuple(
                result.model_copy(
                    update={
                        "evaluation_run_id": recent_run_id,
                        "evaluation_timestamp": recent_time,
                    }
                )
                for result in old.results
            ),
        }
    )
    database.record_evaluation(old)
    database.record_evaluation(recent)
    database.record_alert_attempt(
        AlertAttempt(
            attempt_id="retention-protected-alert",
            invariant_id="RP-CIRC-001",
            adapter="console",
            action="send_new",
            attempted_at=TIMESTAMP,
            result=AlertAttemptResult.SUCCESS,
            duration_seconds=0.01,
            error_category=None,
        )
    )

    report = database.prune_evaluation_details(before=TIMESTAMP + timedelta(days=1))
    restarted = Database(database.path)

    assert report.deleted_result_count == len(old.results)
    assert database.evaluation_results(old.evaluation_run_id) == ()
    assert database.evaluation_results(recent.evaluation_run_id) == recent.results
    old_summary = restarted.evaluation_summary(old.evaluation_run_id)
    recent_summary = restarted.evaluation_summary(recent.evaluation_run_id)
    assert old_summary.result_count == len(old.results)
    assert old_summary.detail_retained is False
    assert recent_summary.result_count == len(recent.results)
    assert recent_summary.detail_retained is True
    assert restarted.evaluation_run_count() == 2
    assert restarted.snapshot_count() == 1
    assert restarted.transition_count("RP-CIRC-001") == 1
    assert restarted.active_finding("RP-CIRC-001") is not None
    assert restarted.alert_attempt_count("RP-CIRC-001") == 1


def test_retention_keeps_detail_at_exact_cutoff(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    run = _evaluation()
    database.record_evaluation(run)

    report = database.prune_evaluation_details(before=TIMESTAMP)

    assert report.deleted_result_count == 0
    assert database.evaluation_results(run.evaluation_run_id) == run.results
