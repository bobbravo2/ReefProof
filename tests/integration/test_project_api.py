"""Authenticated project API integration tests for ADR 0003."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pyotp

from reefproof.api import create_app
from reefproof.project_state import (
    PROJECT_ID,
    PROJECT_NAME,
    AcceptedFactRecord,
    Actor,
    ActorRole,
    CandidateDecisionKind,
    CandidateFact,
    CandidateValidation,
    InterviewSession,
    Project,
    decide_candidate,
)
from reefproof.project_store import ProjectStore
from reefproof.service import RuntimeState
from reefproof.storage import Database

NOW = datetime(2026, 7, 25, 20, tzinfo=UTC)
LATER = datetime(2026, 7, 25, 21, tzinfo=UTC)
TOKEN = "local-test-operator-token"


def _runtime_state() -> RuntimeState:
    return RuntimeState.model_validate(
        {
            "started_at": NOW - timedelta(hours=1),
            "operating_mode": "fixture",
            "hydros_connection": "disabled",
            "mqtt_connection": "disabled",
            "last_valid_configuration_at": None,
            "last_configuration_change_at": None,
            "configuration_hash": None,
            "last_evaluation_at": None,
            "last_evaluation_duration_seconds": None,
            "latest_evaluated_configuration_hash": None,
            "policy_loaded": True,
            "policy_hash": None,
            "annotation_hash": None,
            "storage_writable": True,
            "unrecoverable_transport_failure": None,
            "alert_delivery_state": "unverified",
            "maximum_configuration_age_seconds": 600,
        }
    )


async def _request(
    app,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers, json=json)


def _app(database: Database, *, now: datetime = NOW):
    project_store = ProjectStore(database.path)
    project_store.ensure_project(
        Project(
            project_id=PROJECT_ID,
            name=PROJECT_NAME,
            acceptance_authority_principal_id="acceptance-authority",
            created_at=now,
        )
    )
    return create_app(
        runtime_state=_runtime_state,
        database=database,
        now=lambda: now,
        bootstrap_secret=TOKEN,
        project_store=project_store,
        acceptance_principal_id="acceptance-authority",
        acceptance_principal_display_name="Acceptance authority",
    )


def _operator_headers(app) -> dict[str, str]:
    response = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/operator-sessions",
            json={"bootstrap_secret": TOKEN},
        )
    )
    assert response.status_code == 201
    cookie = response.cookies.get("reefproof_session")
    assert cookie is not None
    return {"Cookie": f"reefproof_session={cookie}"}


def _enroll_totp(
    app,
    headers: dict[str, str],
    state_path: Path,
    *,
    at: datetime,
) -> str:
    enrollment = asyncio.run(
        _request(app, "POST", "/v1/workbench/totp/enrollment", headers=headers)
    )
    assert enrollment.status_code == 201
    secret = json.loads(state_path.read_text(encoding="utf-8"))["secret"]
    confirmed = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/totp/enrollment/confirm",
            headers=headers,
            json={
                "challenge_id": enrollment.json()["challenge_id"],
                "totp_code": pyotp.TOTP(secret).at(at),
            },
        )
    )
    assert confirmed.status_code == 204
    return secret


def _seed_candidate(store: ProjectStore, *, suffix: str = "return-flow") -> CandidateFact:
    session = InterviewSession(
        session_id=f"session-{suffix}",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=NOW,
        purpose="Resolve a typed commissioning unknown",
        scope_subject_ids=("return_pump",),
    )
    candidate = CandidateFact(
        candidate_fact_id=f"candidate-{suffix}",
        project_id=PROJECT_ID,
        subject_id="return_pump",
        attribute="physical.elevation_inches",
        proposed_value=48,
        proposed_by_actor_id="acceptance-authority",
        proposed_at=NOW,
        evidence_ids=(f"evidence-{suffix}",),
    )
    store.record_session(session)
    store.record_candidate(session.session_id, candidate)
    return candidate


def _seed_accepted_phase(
    store: ProjectStore,
    *,
    suffix: str = "project-phase",
    accepted_at: datetime = NOW,
    sequence: int = 1,
) -> CandidateFact:
    session = InterviewSession(
        session_id=f"session-{suffix}",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=accepted_at,
        purpose="Establish project posture.",
        scope_subject_ids=(PROJECT_ID,),
    )
    candidate = CandidateFact(
        candidate_fact_id=f"candidate-{suffix}",
        project_id=PROJECT_ID,
        subject_id=PROJECT_ID,
        attribute="project.phase",
        proposed_value="operational",
        proposed_by_actor_id="acceptance-authority",
        proposed_at=accepted_at,
        evidence_ids=(f"evidence-{suffix}",),
    )
    validation = CandidateValidation(
        candidate_fact_id=candidate.candidate_fact_id,
        schema_valid=True,
        domain_valid=True,
        reason_codes=(),
        validated_at=accepted_at,
    )
    decision, event = decide_candidate(
        project=store.load_project(PROJECT_ID),
        candidate=candidate,
        validation=validation,
        deciding_actor=Actor(
            actor_id="acceptance-authority",
            display_name="Acceptance authority",
            role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
        ),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id=f"decision-{suffix}",
        decided_at=accepted_at,
        rationale="Accepted posture evidence.",
        next_event_id=f"event-{suffix}",
        next_sequence=sequence,
    )
    assert event is not None
    store.record_session(session)
    store.record_accepted_fact(
        session.session_id,
        AcceptedFactRecord(candidate=candidate, decision=decision, event=event),
    )
    return candidate


def test_operator_auth_and_totp_lifecycle_events_are_logged(
    tmp_path: Path,
    caplog,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    bootstrap_secret_headers = _operator_headers(app)
    secret = _enroll_totp(
        app,
        bootstrap_secret_headers,
        tmp_path / "operator-totp.json",
        at=NOW,
    )

    totp_session = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/operator-sessions",
            json={"totp_code": pyotp.TOTP(secret).at(NOW + timedelta(seconds=30))},
        )
    )
    assert totp_session.status_code == 201

    logout = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/operator-sessions/current/revocations",
            headers=bootstrap_secret_headers,
            json={},
        )
    )
    assert logout.status_code == 204

    messages = [record.getMessage() for record in caplog.records if record.name == "uvicorn.error"]
    assert any(
        "operator.session_established method=bootstrap_secret principal_id=acceptance-authority"
        in message
        for message in messages
    )
    assert any(
        "operator.totp_enrollment_started principal_id=acceptance-authority" in message
        for message in messages
    )
    assert any(
        "operator.totp_enrollment_confirmed principal_id=acceptance-authority" in message
        for message in messages
    )
    assert any(
        "operator.session_established method=totp principal_id=acceptance-authority" in message
        for message in messages
    )
    assert any(
        "operator.session_revoked principal_id=acceptance-authority" in message
        for message in messages
    )


def test_project_reads_are_authenticated_typed_and_no_llm(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    store = ProjectStore(database.path)
    candidate = _seed_candidate(store)

    unauthenticated = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}/state"))
    assert unauthenticated.status_code == 401

    headers = _operator_headers(app)
    description = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}", headers=headers))
    state = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}/state", headers=headers))
    brief = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}/brief", headers=headers))
    sessions = asyncio.run(
        _request(app, "GET", f"/v1/projects/{PROJECT_ID}/sessions", headers=headers)
    )
    candidates = asyncio.run(
        _request(app, "GET", f"/v1/projects/{PROJECT_ID}/candidates", headers=headers)
    )

    assert description.status_code == 200
    assert description.json() == {
        "project_id": PROJECT_ID,
        "canonical": ["state"],
        "derived": ["brief"],
        "candidate": ["candidates"],
        "historical": ["sessions"],
        "llm_required": False,
        "runtime_authority": "HYDROS",
        "control_capability": "none",
    }
    assert state.json() == {
        "project_id": PROJECT_ID,
        "facts": [],
        "applied_event_ids": [],
        "last_sequence": 0,
    }
    assert brief.json()["recommended_next_action"]["status"] == "UNKNOWN"
    assert brief.json()["current_posture"]["posture"] == "UNKNOWN"
    assert sessions.json()[0]["initiated_by_actor_id"] == "acceptance-authority"
    assert candidates.json()[0]["candidate"]["candidate_fact_id"] == (candidate.candidate_fact_id)
    assert candidates.json()[0]["decision"] is None


def test_trust_revocation_is_authority_bound_and_immediately_replayed(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    candidate = _seed_candidate(ProjectStore(database.path), suffix="trust-api")
    headers = _operator_headers(app)
    accepted = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/candidates/{candidate.candidate_fact_id}/review",
            headers=headers,
            json={"decision": "accepted", "rationale": "Verified measurement."},
        )
    )
    assert accepted.status_code == 201
    secret = _enroll_totp(app, headers, tmp_path / "operator-totp.json", at=NOW)
    revocation_code = pyotp.TOTP(secret).at(NOW + timedelta(seconds=30))

    unauthenticated = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            json={
                "scope_kind": "evidence",
                "scope_id": candidate.evidence_ids[0],
                "rationale": "No session.",
                "totp_code": revocation_code,
            },
        )
    )
    assert unauthenticated.status_code == 401
    unknown = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            headers=headers,
            json={
                "scope_kind": "evidence",
                "scope_id": "evidence-does-not-exist",
                "rationale": "Unknown scope.",
                "totp_code": revocation_code,
            },
        )
    )
    assert unknown.status_code == 404
    revoked = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            headers=headers,
            json={
                "scope_kind": "evidence",
                "scope_id": candidate.evidence_ids[0],
                "rationale": "Calibration chain was withdrawn.",
                "totp_code": revocation_code,
            },
        )
    )
    assert revoked.status_code == 201
    assert revoked.json()["active_revocations"][0]["scope_id"] == candidate.evidence_ids[0]
    duplicate = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            headers=headers,
            json={
                "scope_kind": "evidence",
                "scope_id": candidate.evidence_ids[0],
                "rationale": "Duplicate.",
                "totp_code": revocation_code,
            },
        )
    )
    assert duplicate.status_code == 409


def test_project_brief_retains_evaluated_posture_but_revokes_effective_posture(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    candidate = _seed_accepted_phase(ProjectStore(database.path))
    headers = _operator_headers(app)
    before = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}/brief", headers=headers))
    assert before.json()["current_posture"]["posture"] == "operational"
    assert before.json()["current_posture"]["evaluated_posture"] == "operational"
    assert before.json()["current_posture"]["trust_status"] == "TRUSTED"
    secret = _enroll_totp(app, headers, tmp_path / "operator-totp.json", at=NOW)

    revoked = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            headers=headers,
            json={
                "scope_kind": "evidence",
                "scope_id": candidate.evidence_ids[0],
                "rationale": "The commissioning record was withdrawn.",
                "totp_code": pyotp.TOTP(secret).at(NOW + timedelta(seconds=30)),
            },
        )
    )
    event_id = revoked.json()["active_revocations"][0]["trust_event_id"]
    after = asyncio.run(_request(app, "GET", f"/v1/projects/{PROJECT_ID}/brief", headers=headers))
    posture = after.json()["current_posture"]
    assert posture["evaluated_posture"] == "operational"
    assert posture["posture"] == "UNKNOWN"
    assert posture["trust_status"] == "REVOKED"
    assert posture["contributing_trust_event_ids"] == [event_id]


def test_fresh_evidence_and_new_totp_counter_restore_project_brief(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    store = ProjectStore(database.path)
    store.ensure_project(
        Project(
            project_id=PROJECT_ID,
            name=PROJECT_NAME,
            acceptance_authority_principal_id="acceptance-authority",
            created_at=NOW,
        )
    )
    original = _seed_accepted_phase(store)
    clock = [NOW + timedelta(seconds=1)]
    app = create_app(
        runtime_state=_runtime_state,
        database=database,
        now=lambda: clock[0],
        bootstrap_secret=TOKEN,
        project_store=store,
        acceptance_principal_id="acceptance-authority",
        acceptance_principal_display_name="Acceptance authority",
    )
    headers = _operator_headers(app)
    secret = _enroll_totp(
        app,
        headers,
        tmp_path / "operator-totp.json",
        at=clock[0],
    )
    clock[0] += timedelta(seconds=30)
    revoked = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/revocations",
            headers=headers,
            json={
                "scope_kind": "evidence",
                "scope_id": original.evidence_ids[0],
                "rationale": "Original commissioning record withdrawn.",
                "totp_code": pyotp.TOTP(secret).at(clock[0]),
            },
        )
    )
    revocation_id = revoked.json()["active_revocations"][0]["trust_event_id"]
    replacement = _seed_accepted_phase(
        store,
        suffix="project-phase-replacement",
        accepted_at=LATER,
        sequence=2,
    )
    clock[0] = LATER + timedelta(seconds=1)

    restored = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/trust/restorations",
            headers=headers,
            json={
                "revocation_id": revocation_id,
                "rationale": "Fresh commissioning evidence accepted.",
                "replacement_candidate_fact_ids": [replacement.candidate_fact_id],
                "totp_code": pyotp.TOTP(secret).at(clock[0]),
            },
        )
    )
    assert restored.status_code == 201
    assert restored.json()["active_revocations"] == []
    brief = asyncio.run(
        _request(app, "GET", f"/v1/projects/{PROJECT_ID}/brief", headers=headers)
    ).json()
    assert brief["current_posture"]["posture"] == "operational"
    assert brief["current_posture"]["evaluated_posture"] == "operational"
    assert brief["current_posture"]["trust_status"] == "TRUSTED"


def test_totp_enrollment_is_authenticated_one_time_and_no_store(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    assert asyncio.run(_request(app, "POST", "/v1/workbench/totp/enrollment")).status_code == 401
    headers = _operator_headers(app)
    enrollment = asyncio.run(
        _request(app, "POST", "/v1/workbench/totp/enrollment", headers=headers)
    )
    assert enrollment.status_code == 201
    assert enrollment.headers["cache-control"] == "no-store"
    state_path = tmp_path / "operator-totp.json"
    secret = json.loads(state_path.read_text(encoding="utf-8"))["secret"]
    confirmed = asyncio.run(
        _request(
            app,
            "POST",
            "/v1/workbench/totp/enrollment/confirm",
            headers=headers,
            json={
                "challenge_id": enrollment.json()["challenge_id"],
                "totp_code": pyotp.TOTP(secret).at(NOW),
            },
        )
    )
    assert confirmed.status_code == 204
    again = asyncio.run(_request(app, "POST", "/v1/workbench/totp/enrollment", headers=headers))
    assert again.status_code == 409


def test_candidate_review_rejects_a_session_for_a_different_principal(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    project_store = ProjectStore(database.path)
    project_store.ensure_project(
        Project(
            project_id=PROJECT_ID,
            name=PROJECT_NAME,
            acceptance_authority_principal_id="acceptance-authority",
            created_at=NOW,
        )
    )
    candidate = _seed_candidate(project_store, suffix="principal-mismatch")
    app = create_app(
        runtime_state=_runtime_state,
        database=database,
        now=lambda: NOW,
        bootstrap_secret=TOKEN,
        project_store=project_store,
        acceptance_principal_id="different-authority",
        acceptance_principal_display_name="Different authority",
    )

    response = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/candidates/{candidate.candidate_fact_id}/review",
            headers=_operator_headers(app),
            json={"decision": "rejected", "rationale": "Not my project authority."},
        )
    )

    assert response.status_code == 403
    assert project_store.load_candidate(candidate.candidate_fact_id).decision is None


def test_acceptance_authority_rejection_survives_restart_without_canonical_event(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    candidate = _seed_candidate(ProjectStore(database.path), suffix="reject")
    headers = _operator_headers(app)

    response = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/candidates/{candidate.candidate_fact_id}/review",
            headers=headers,
            json={
                "decision": "rejected",
                "rationale": "The observation does not identify the active operating mode.",
            },
        )
    )

    assert response.status_code == 201
    assert response.json()["decision"]["decision"] == "rejected"
    assert response.json()["canonical_state"]["applied_event_ids"] == []

    restarted = _app(database, now=LATER)
    restarted_headers = _operator_headers(restarted)
    candidates = asyncio.run(
        _request(
            restarted,
            "GET",
            f"/v1/projects/{PROJECT_ID}/candidates",
            headers=restarted_headers,
        )
    )
    state = asyncio.run(
        _request(
            restarted,
            "GET",
            f"/v1/projects/{PROJECT_ID}/state",
            headers=restarted_headers,
        )
    )
    assert candidates.json()[0]["decision"]["decision"] == "rejected"
    assert state.json()["facts"] == []
    assert state.json()["applied_event_ids"] == []


def test_acceptance_authority_acceptance_atomically_becomes_canonical_fact(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    candidate = _seed_candidate(ProjectStore(database.path), suffix="accept")
    headers = _operator_headers(app)

    response = asyncio.run(
        _request(
            app,
            "POST",
            f"/v1/projects/{PROJECT_ID}/candidates/{candidate.candidate_fact_id}/review",
            headers=headers,
            json={
                "decision": "accepted",
                "rationale": "Direct observation and pump specification agree.",
            },
        )
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["decision"]["decided_by_actor_id"] == "acceptance-authority"
    assert payload["decision"]["resulting_domain_event_id"].startswith("event-")
    assert payload["canonical_state"]["last_sequence"] == 1
    assert payload["canonical_state"]["facts"] == [
        {
            "subject_id": "return_pump",
            "attribute": "physical.elevation_inches",
            "value": 48,
            "source_candidate_fact_id": candidate.candidate_fact_id,
            "accepted_by_actor_id": "acceptance-authority",
            "accepted_at": NOW.isoformat().replace("+00:00", "Z"),
            "evidence_ids": ["evidence-accept"],
            "epistemic_state": "fact",
        }
    ]

    store = ProjectStore(database.path)
    records = store.accepted_fact_records(PROJECT_ID)
    assert len(records) == 1
    assert records[0].decision.resulting_domain_event_id == records[0].event.event_id

    restarted = _app(database, now=LATER)
    restarted_headers = _operator_headers(restarted)
    restarted_state = asyncio.run(
        _request(
            restarted,
            "GET",
            f"/v1/projects/{PROJECT_ID}/state",
            headers=restarted_headers,
        )
    )
    restarted_brief = asyncio.run(
        _request(
            restarted,
            "GET",
            f"/v1/projects/{PROJECT_ID}/brief",
            headers=restarted_headers,
        )
    )
    assert restarted_state.json() == payload["canonical_state"]
    assert (
        restarted_brief.json()["recent_accepted_decisions"][0]["source_candidate_fact_id"]
        == candidate.candidate_fact_id
    )


def test_invalid_acceptance_and_repeat_review_fail_closed(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    candidate = _seed_candidate(ProjectStore(database.path), suffix="invalid")
    store = ProjectStore(database.path)
    unsupported = CandidateFact(
        **{
            **candidate.model_dump(),
            "candidate_fact_id": "candidate-unsupported",
            "attribute": "equipment.minimum_flow_gph",
        }
    )
    unsupported_session = InterviewSession(
        session_id="session-unsupported",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=NOW,
        purpose="Test an unsupported validation domain",
        scope_subject_ids=("return_pump",),
    )
    store.record_session(unsupported_session)
    store.record_candidate(unsupported_session.session_id, unsupported)
    headers = _operator_headers(app)
    path = f"/v1/projects/{PROJECT_ID}/candidates/{unsupported.candidate_fact_id}/review"

    invalid = asyncio.run(
        _request(
            app,
            "POST",
            path,
            headers=headers,
            json={
                "decision": "accepted",
                "rationale": "Accept despite missing validation.",
            },
        )
    )
    assert invalid.status_code == 409
    assert (
        ProjectStore(database.path).load_candidate(unsupported.candidate_fact_id).decision is None
    )
    restarted = _app(database, now=LATER)
    restarted_headers = _operator_headers(restarted)
    restarted_state = asyncio.run(
        _request(
            restarted,
            "GET",
            f"/v1/projects/{PROJECT_ID}/state",
            headers=restarted_headers,
        )
    )
    assert restarted_state.json()["facts"] == []
    assert (
        ProjectStore(database.path).load_candidate(unsupported.candidate_fact_id).decision is None
    )

    rejected = asyncio.run(
        _request(
            restarted,
            "POST",
            path,
            headers=restarted_headers,
            json={
                "decision": "rejected",
                "rationale": "Validation is incomplete.",
            },
        )
    )
    repeated = asyncio.run(
        _request(
            restarted,
            "POST",
            path,
            headers=restarted_headers,
            json={
                "decision": "rejected",
                "rationale": "Try to rewrite the audit record.",
            },
        )
    )
    assert rejected.status_code == 201
    assert repeated.status_code == 409


def test_project_api_has_no_general_or_controller_mutation_routes(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    app = _app(database)
    headers = _operator_headers(app)

    for method, path, expected in (
        ("PUT", f"/v1/projects/{PROJECT_ID}/state", 405),
        ("PATCH", f"/v1/projects/{PROJECT_ID}/state", 405),
        ("DELETE", f"/v1/projects/{PROJECT_ID}/state", 405),
        ("POST", f"/v1/projects/{PROJECT_ID}/equipment/return-pump", 404),
        ("POST", f"/v1/projects/{PROJECT_ID}/hydros/outputs", 404),
        ("POST", f"/v1/projects/{PROJECT_ID}/mqtt", 404),
    ):
        response = asyncio.run(_request(app, method, path, headers=headers, json={}))
        assert response.status_code == expected

    source = Path("src/reefproof/api/projects.py").read_text()
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        module.startswith(
            (
                "reefproof.alerting",
                "reefproof.service.pipeline",
                "reefproof.transport",
            )
        )
        for module in imported_modules
    )
