"""Authenticated project projections and authority-bound candidate review."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from reefproof.api.sessions import AuthenticatedSession, OperatorSessions, SessionDependencies
from reefproof.auth_totp import TotpState
from reefproof.candidate_validation import validate_candidate
from reefproof.project_brief import ProjectBrief, project_brief
from reefproof.project_state import (
    PROJECT_ID,
    AcceptedFactRecord,
    Actor,
    ActorRole,
    CandidateDecision,
    CandidateDecisionKind,
    CandidateFact,
    InterviewSession,
    ProjectState,
    decide_candidate,
)
from reefproof.project_store import ProjectStore, StoredCandidate
from reefproof.trust import TrustEvent, TrustScopeKind, TrustState


class FrozenApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CandidateReviewRequest(FrozenApiModel):
    """An explicit human decision; validation is computed by ReefProof."""

    decision: CandidateDecisionKind
    rationale: str = Field(min_length=1)


class CandidateReviewResponse(FrozenApiModel):
    candidate: CandidateFact
    decision: CandidateDecision
    canonical_state: ProjectState


class ProjectApiDescription(FrozenApiModel):
    project_id: str = Field(default=PROJECT_ID, pattern=r"^[a-z][a-z0-9_-]*$")
    canonical: tuple[str, ...] = ("state",)
    derived: tuple[str, ...] = ("brief",)
    candidate: tuple[str, ...] = ("candidates",)
    historical: tuple[str, ...] = ("sessions",)
    llm_required: Literal[False] = False
    runtime_authority: Literal["HYDROS"] = "HYDROS"
    control_capability: Literal["none"] = "none"


class TrustRevocationRequest(FrozenApiModel):
    scope_kind: TrustScopeKind
    scope_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    totp_code: str = Field(pattern=r"^\d{6}$")


class TrustRestorationRequest(FrozenApiModel):
    revocation_id: str
    rationale: str = Field(min_length=1)
    replacement_candidate_fact_ids: tuple[str, ...] = Field(min_length=1)
    totp_code: str = Field(pattern=r"^\d{6}$")


def register_project_routes(
    app: FastAPI,
    *,
    store: ProjectStore,
    operator_sessions: OperatorSessions,
    session_dependencies: SessionDependencies,
    now: Callable[[], datetime],
    totp: TotpState | None = None,
    active_project_id: str = PROJECT_ID,
) -> None:
    """Register the fixed v0.1 project API without controller dependencies."""

    required_session = Depends(session_dependencies.required)

    def operator_actor(session: AuthenticatedSession) -> Actor:
        principal = session.principal
        return Actor(
            actor_id=principal.principal_id,
            display_name=principal.display_name,
            role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
        )

    def require_project(project_id: str) -> None:
        if project_id != active_project_id:
            raise HTTPException(status_code=404, detail="project not found")

    def require_authority(project_id: str, session: AuthenticatedSession) -> Actor:
        actor = operator_actor(session)
        project = store.load_project(project_id)
        if actor.actor_id != project.acceptance_authority_principal_id:
            raise HTTPException(status_code=403, detail="project authority required")
        return actor

    @app.get(
        "/v1/projects/{project_id}",
        response_model=ProjectApiDescription,
    )
    def project_description(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> ProjectApiDescription:
        require_project(project_id)
        return ProjectApiDescription(project_id=active_project_id)

    @app.get(
        "/v1/projects/{project_id}/state",
        response_model=ProjectState,
    )
    def project_state(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> ProjectState:
        require_project(project_id)
        return store.replay(project_id)

    @app.get(
        "/v1/projects/{project_id}/brief",
        response_model=ProjectBrief,
    )
    def get_project_brief(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> ProjectBrief:
        require_project(project_id)
        return project_brief(
            state=store.replay(project_id),
            trust=store.replay_trust(project_id),
        )

    @app.get(
        "/v1/projects/{project_id}/sessions",
        response_model=tuple[InterviewSession, ...],
    )
    def project_sessions(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> tuple[InterviewSession, ...]:
        require_project(project_id)
        return store.list_sessions(project_id)

    @app.get(
        "/v1/projects/{project_id}/sessions/{interview_session_id}",
        response_model=InterviewSession,
    )
    def project_session(
        project_id: str,
        interview_session_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> InterviewSession:
        require_project(project_id)
        try:
            session = store.load_session(interview_session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="interview session not found") from error
        if session.project_id != project_id:
            raise HTTPException(status_code=404, detail="interview session not found")
        return session

    @app.get(
        "/v1/projects/{project_id}/candidates",
        response_model=tuple[StoredCandidate, ...],
    )
    def project_candidates(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> tuple[StoredCandidate, ...]:
        require_project(project_id)
        return store.list_candidates(project_id)

    @app.get(
        "/v1/projects/{project_id}/trust",
        response_model=TrustState,
    )
    def project_trust(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> TrustState:
        require_project(project_id)
        return store.replay_trust(project_id)

    @app.post(
        "/v1/projects/{project_id}/trust/revocations",
        response_model=TrustState,
        status_code=201,
    )
    def revoke_trust(
        project_id: str,
        request: TrustRevocationRequest,
        session: AuthenticatedSession = required_session,
    ) -> TrustState:
        require_project(project_id)
        actor = require_authority(project_id, session)
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            roots = store.trust_roots(project_id, request.scope_kind, request.scope_id)
            state = store.replay_trust(project_id)
            verified_at = totp.verify(request.totp_code)
            return store.append_trust_event(
                TrustEvent(
                    trust_event_id=f"trust-{uuid4()}",
                    project_id=project_id,
                    sequence=state.last_sequence + 1,
                    event_type="revoked",
                    occurred_at=now(),
                    actor_id=actor.actor_id,
                    rationale=request.rationale,
                    scope_kind=request.scope_kind,
                    scope_id=request.scope_id,
                    affected_roots=roots,
                    totp_verified_at=verified_at,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/v1/projects/{project_id}/trust/restorations",
        response_model=TrustState,
        status_code=201,
    )
    def restore_trust(
        project_id: str,
        request: TrustRestorationRequest,
        session: AuthenticatedSession = required_session,
    ) -> TrustState:
        require_project(project_id)
        actor = require_authority(project_id, session)
        state = store.replay_trust(project_id)
        revocation = next(
            (
                event
                for event in state.active_revocations
                if event.trust_event_id == request.revocation_id
            ),
            None,
        )
        if revocation is None:
            raise HTTPException(status_code=409, detail="active revocation not found")
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            evidence_ids = store.validate_restoration_candidates(
                revocation,
                request.replacement_candidate_fact_ids,
            )
            verified_at = totp.verify(request.totp_code)
            return store.append_trust_event(
                TrustEvent(
                    trust_event_id=f"trust-{uuid4()}",
                    project_id=project_id,
                    sequence=state.last_sequence + 1,
                    event_type="restored",
                    occurred_at=now(),
                    actor_id=actor.actor_id,
                    rationale=request.rationale,
                    scope_kind=revocation.scope_kind,
                    scope_id=revocation.scope_id,
                    affected_roots=revocation.affected_roots,
                    linked_revocation_id=revocation.trust_event_id,
                    replacement_candidate_fact_ids=request.replacement_candidate_fact_ids,
                    replacement_evidence_ids=evidence_ids,
                    totp_verified_at=verified_at,
                )
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/v1/projects/{project_id}/candidates/{candidate_fact_id}/review",
        response_model=CandidateReviewResponse,
        status_code=201,
    )
    def review_candidate(
        project_id: str,
        candidate_fact_id: str,
        request: CandidateReviewRequest,
        session: AuthenticatedSession = required_session,
    ) -> CandidateReviewResponse:
        deciding_actor = operator_actor(session)
        require_project(project_id)
        try:
            stored = store.load_candidate(candidate_fact_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="candidate fact not found") from error
        if stored.candidate.project_id != project_id:
            raise HTTPException(status_code=404, detail="candidate fact not found")
        if stored.decision is not None:
            raise HTTPException(status_code=409, detail="candidate already reviewed")

        timestamp = now()
        validation = validate_candidate(stored.candidate, validated_at=timestamp)
        project = store.load_project(project_id)
        try:
            decision, event = decide_candidate(
                project=project,
                candidate=stored.candidate,
                validation=validation,
                deciding_actor=deciding_actor,
                decision=request.decision,
                decision_id=f"decision-{uuid4()}",
                decided_at=timestamp,
                rationale=request.rationale,
                next_event_id=(
                    f"event-{uuid4()}"
                    if request.decision is CandidateDecisionKind.ACCEPTED
                    else None
                ),
                next_sequence=(
                    store.replay(project_id).last_sequence + 1
                    if request.decision is CandidateDecisionKind.ACCEPTED
                    else None
                ),
            )
            if event is None:
                store.record_rejection(stored.session_id, stored.candidate, decision)
            else:
                store.record_accepted_fact(
                    stored.session_id,
                    AcceptedFactRecord(
                        candidate=stored.candidate,
                        decision=decision,
                        event=event,
                    ),
                )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return CandidateReviewResponse(
            candidate=stored.candidate,
            decision=decision,
            canonical_state=store.replay(project_id),
        )
