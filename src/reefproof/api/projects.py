"""Authenticated project projections and authority-bound candidate review."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from reefproof import __version__
from reefproof.api.sessions import AuthenticatedSession, OperatorSessions, SessionDependencies
from reefproof.auth_totp import TotpState
from reefproof.authored_sources import (
    AuthoredImportBatch,
    AuthoredImportReview,
    AuthoredSourceConfiguration,
    AuthoredSourceStatus,
    AuthoredSourceStore,
    AuthoredSystemSource,
    ExternalIdentityBinding,
    authored_source_status,
    build_import_review,
    load_authored_source,
)
from reefproof.authored_sources.acceptance import accept_source_session, reject_source_session
from reefproof.candidate_validation import validate_candidate
from reefproof.commissioning import (
    CommissioningProjection,
    CommissioningVerification,
    FailureModeDisposition,
    FailureModeDispositionKind,
    LabelEndpoint,
    VerificationKind,
    VerificationOutcome,
    commissioning_projection,
)
from reefproof.commissioning_store import CommissioningStore
from reefproof.labels import (
    LabelManifest,
    generate_label_manifest,
    label_export_filename,
    render_label_csv,
)
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
from reefproof.reconciliation import ReconciliationProjection, reconciliation_projection
from reefproof.storage import Database
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


class AuthoredImportSummary(FrozenApiModel):
    import_batch_id: str
    fetched_at: datetime
    source_snapshot_hash: str
    normalized_content_hash: str
    valid: bool
    record_counts: dict[str, int]
    diagnostic_count: int
    review_status: Literal["INVALID", "PENDING_REVIEW", "ACCEPTED", "REJECTED"]


class AuthoredImportReviewRequest(FrozenApiModel):
    decision: Literal["ACCEPTED", "REJECTED"]
    rationale: str = Field(min_length=1)
    totp_code: str = Field(pattern=r"^\d{6}$")


class AuthoredImportReviewResponse(FrozenApiModel):
    import_batch_id: str
    decision: Literal["ACCEPTED", "REJECTED"]
    reviewed_candidate_count: int
    project_sequence: int


class CommissioningVerificationRequest(FrozenApiModel):
    device_id: str
    kind: VerificationKind
    outcome: VerificationOutcome
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    connection_id: str | None = None
    control_surface_id: str | None = None
    manifest_id: str | None = None
    label_id: str | None = None
    label_endpoint: LabelEndpoint | None = None
    totp_code: str = Field(pattern=r"^\d{6}$")


class FailureModeDispositionRequest(FrozenApiModel):
    device_id: str
    failure_mode_id: str = Field(min_length=1)
    disposition: FailureModeDispositionKind
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    totp_code: str = Field(pattern=r"^\d{6}$")


class ObservedIdentityBindingRequest(FrozenApiModel):
    canonical_device_id: str = Field(min_length=1)
    observed_entity_id: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    totp_code: str = Field(pattern=r"^\d{6}$")


class ProjectApiDescription(FrozenApiModel):
    project_id: str = Field(default=PROJECT_ID, pattern=r"^[a-z][a-z0-9_-]*$")
    canonical: tuple[str, ...] = ("state",)
    derived: tuple[str, ...] = (
        "brief",
        "authored-sources",
        "imports",
        "reconciliation",
        "commissioning",
        "labels",
        "labels.csv",
    )
    candidate: tuple[str, ...] = (
        "candidates",
        "imports/{import_batch_id}/review",
        "reconciliation/bindings",
        "commissioning/verifications",
        "commissioning/failure-mode-dispositions",
        "commissioning/label-verifications",
    )
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
    authored_source: AuthoredSystemSource | None = None,
    authored_source_freshness_seconds: int = 900,
) -> None:
    """Register the fixed v0.1 project API without controller dependencies."""

    required_session = Depends(session_dependencies.required)
    source_store = AuthoredSourceStore(store.path)
    commissioning_store = CommissioningStore(store.path)
    database = Database(store.path)

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

    def import_session_id(import_batch_id: str) -> str:
        return f"session-source-{import_batch_id.replace('-', '')}"

    def import_review_status(
        import_batch_id: str,
    ) -> Literal["PENDING_REVIEW", "ACCEPTED", "REJECTED"]:
        try:
            source_session = store.load_session(import_session_id(import_batch_id))
        except KeyError:
            return "PENDING_REVIEW"
        if not source_session.decisions:
            return "PENDING_REVIEW"
        if all(
            item.decision is CandidateDecisionKind.ACCEPTED for item in source_session.decisions
        ):
            return "ACCEPTED"
        return "REJECTED"

    def import_summary(batch: AuthoredImportBatch) -> AuthoredImportSummary:
        return AuthoredImportSummary(
            import_batch_id=batch.import_batch_id,
            fetched_at=batch.fetched_at,
            source_snapshot_hash=batch.source_snapshot_hash,
            normalized_content_hash=batch.normalized_content_hash,
            valid=batch.valid,
            record_counts={key.value: value for key, value in batch.record_counts.items()},
            diagnostic_count=len(batch.diagnostics),
            review_status=(
                "INVALID" if not batch.valid else import_review_status(batch.import_batch_id)
            ),
        )

    def require_device(project_id: str, device_id: str) -> None:
        if not any(
            fact.subject_id == device_id and fact.attribute == "identity.external_id"
            for fact in store.replay(project_id).facts
        ):
            raise HTTPException(status_code=404, detail="canonical device not found")

    def commissioning_state(project_id: str) -> CommissioningProjection:
        project = store.load_project(project_id)
        reconciliation = reconciliation_projection(
            state=store.replay(project_id),
            bindings=source_store.list_bindings(project_id),
            observed_snapshot=database.latest_snapshot(),
        )
        return commissioning_projection(
            state=store.replay(project_id),
            bindings=source_store.list_bindings(project_id),
            label_manifest=generate_label_manifest(
                store.replay(project_id),
                project_name=project.name,
                bindings=source_store.list_bindings(project_id),
            ),
            verifications=commissioning_store.list_verifications(project_id),
            dispositions=commissioning_store.list_dispositions(project_id),
            blocking_conflict_subject_ids=reconciliation.blocking_subject_ids,
        )

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
        "/v1/projects/{project_id}/authored-sources",
        response_model=tuple[AuthoredSourceConfiguration, ...],
    )
    def project_authored_sources(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> tuple[AuthoredSourceConfiguration, ...]:
        require_project(project_id)
        configuration = source_store.latest_configuration(project_id)
        return () if configuration is None else (configuration,)

    @app.get(
        "/v1/projects/{project_id}/authored-sources/google-sheets/status",
        response_model=AuthoredSourceStatus,
    )
    def project_authored_source_status(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> AuthoredSourceStatus:
        require_project(project_id)
        accepted = next(
            (
                batch
                for batch in source_store.list_imports(project_id)
                if import_review_status(batch.import_batch_id) == "ACCEPTED"
            ),
            None,
        )
        latest_snapshot = source_store.latest_snapshot(project_id)
        latest_fetch_at = source_store.latest_successful_fetch_at(project_id)
        latest_attempt = source_store.latest_fetch_attempt(project_id)
        if latest_snapshot is not None and latest_fetch_at is not None:
            latest_snapshot = latest_snapshot.model_copy(update={"fetched_at": latest_fetch_at})
        return authored_source_status(
            configuration=source_store.latest_configuration(project_id),
            latest_snapshot=latest_snapshot,
            now=now(),
            fetch_error=(
                latest_attempt.error_category
                if latest_attempt is not None and not latest_attempt.succeeded
                else None
            ),
            accepted_snapshot_hash=(None if accepted is None else accepted.source_snapshot_hash),
        )

    @app.post(
        "/v1/projects/{project_id}/authored-sources/google-sheets/sync",
        response_model=AuthoredImportSummary,
        status_code=201,
    )
    def sync_project_authored_source(
        project_id: str,
        session: AuthenticatedSession = required_session,
    ) -> AuthoredImportSummary:
        require_project(project_id)
        require_authority(project_id, session)
        if authored_source is None:
            raise HTTPException(status_code=409, detail="Google Sheets source is not configured")
        project = store.load_project(project_id)
        try:
            loaded = load_authored_source(
                source=authored_source,
                source_store=source_store,
                project_store=store,
                project_id=project_id,
                project_name=project.name,
                acceptance_authority_principal_id=project.acceptance_authority_principal_id,
                freshness_seconds=authored_source_freshness_seconds,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            configuration = source_store.latest_configuration(project_id)
            if configuration is not None:
                source_store.record_fetch_failure(
                    project_id=project_id,
                    source_configuration_id=configuration.source_configuration_id,
                    fetched_at=now(),
                    error_category=type(error).__name__,
                )
            raise HTTPException(
                status_code=502,
                detail="Google Sheets source fetch failed; retained evidence is unchanged",
            ) from error
        return import_summary(loaded.batch)

    @app.get(
        "/v1/projects/{project_id}/imports",
        response_model=tuple[AuthoredImportSummary, ...],
    )
    def project_imports(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> tuple[AuthoredImportSummary, ...]:
        require_project(project_id)
        return tuple(import_summary(batch) for batch in source_store.list_imports(project_id))

    @app.get(
        "/v1/projects/{project_id}/imports/{import_batch_id}",
        response_model=AuthoredImportReview,
    )
    def project_import_review(
        project_id: str,
        import_batch_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> AuthoredImportReview:
        require_project(project_id)
        try:
            batch = source_store.load_import(project_id, import_batch_id)
            configuration = source_store.source_configuration_for_import(
                project_id, import_batch_id
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="authored import not found") from error
        return build_import_review(
            batch,
            project_id=project_id,
            state=store.replay(project_id),
            bindings=source_store.list_bindings(project_id),
            source_instance=configuration.spreadsheet_id,
        )

    @app.post(
        "/v1/projects/{project_id}/imports/{import_batch_id}/review",
        response_model=AuthoredImportReviewResponse,
        status_code=201,
    )
    def review_authored_import(
        project_id: str,
        import_batch_id: str,
        request: AuthoredImportReviewRequest,
        session: AuthenticatedSession = required_session,
    ) -> AuthoredImportReviewResponse:
        require_project(project_id)
        actor = require_authority(project_id, session)
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            source_store.load_import(project_id, import_batch_id)
            verified_at = totp.verify(request.totp_code)
            session_id = import_session_id(import_batch_id)
            if request.decision == "ACCEPTED":
                count, sequence, _ = accept_source_session(
                    project_store=store,
                    source_store=source_store,
                    session_id=session_id,
                    actor=actor,
                    accepted_at=verified_at,
                    rationale=request.rationale,
                )
            else:
                count = reject_source_session(
                    project_store=store,
                    session_id=session_id,
                    actor=actor,
                    rejected_at=verified_at,
                    rationale=request.rationale,
                )
                sequence = store.replay(project_id).last_sequence
        except KeyError as error:
            raise HTTPException(status_code=404, detail="authored import not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return AuthoredImportReviewResponse(
            import_batch_id=import_batch_id,
            decision=request.decision,
            reviewed_candidate_count=count,
            project_sequence=sequence,
        )

    @app.get(
        "/v1/projects/{project_id}/labels",
        response_model=LabelManifest,
    )
    def project_labels(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> LabelManifest:
        require_project(project_id)
        project = store.load_project(project_id)
        return generate_label_manifest(
            store.replay(project_id),
            project_name=project.name,
            bindings=source_store.list_bindings(project_id),
        )

    @app.get("/v1/projects/{project_id}/labels.csv", response_class=Response)
    def project_labels_csv(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> Response:
        require_project(project_id)
        project = store.load_project(project_id)
        manifest = generate_label_manifest(
            store.replay(project_id),
            project_name=project.name,
            bindings=source_store.list_bindings(project_id),
        )
        document = render_label_csv(manifest)
        filename = label_export_filename(project.name, version=__version__)
        return Response(
            content=document,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get(
        "/v1/projects/{project_id}/reconciliation",
        response_model=ReconciliationProjection,
    )
    def project_reconciliation(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> ReconciliationProjection:
        require_project(project_id)
        return reconciliation_projection(
            state=store.replay(project_id),
            bindings=source_store.list_bindings(project_id),
            observed_snapshot=database.latest_snapshot(),
        )

    @app.post(
        "/v1/projects/{project_id}/reconciliation/bindings",
        response_model=ReconciliationProjection,
        status_code=201,
    )
    def bind_observed_identity(
        project_id: str,
        request: ObservedIdentityBindingRequest,
        session: AuthenticatedSession = required_session,
    ) -> ReconciliationProjection:
        require_project(project_id)
        require_authority(project_id, session)
        require_device(project_id, request.canonical_device_id)
        snapshot = database.latest_snapshot()
        if snapshot is None or snapshot.provenance != "OBSERVED":
            raise HTTPException(status_code=409, detail="observed HYDROS evidence is unavailable")
        if not any(
            entity.reefproof_id == request.observed_entity_id for entity in snapshot.entities
        ):
            raise HTTPException(status_code=409, detail="observed entity is absent from evidence")
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            accepted_at = totp.verify(request.totp_code)
            identity = uuid5(
                NAMESPACE_URL,
                f"{project_id}:{snapshot.snapshot_hash}:{request.observed_entity_id}",
            ).hex
            source_store.record_bindings(
                (
                    ExternalIdentityBinding(
                        binding_id=f"binding-{identity}",
                        project_id=project_id,
                        source_system="hydros",
                        source_instance=snapshot.snapshot_hash,
                        namespace="reefproof_id",
                        value=request.observed_entity_id,
                        canonical_subject_id=request.canonical_device_id,
                        evidence_reference=request.evidence_reference,
                        rationale=request.rationale,
                        accepted_at=accepted_at,
                    ),
                )
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return reconciliation_projection(
            state=store.replay(project_id),
            bindings=source_store.list_bindings(project_id),
            observed_snapshot=snapshot,
        )

    @app.get(
        "/v1/projects/{project_id}/commissioning",
        response_model=CommissioningProjection,
    )
    def project_commissioning(
        project_id: str,
        _session: AuthenticatedSession = required_session,
    ) -> CommissioningProjection:
        require_project(project_id)
        return commissioning_state(project_id)

    def record_commissioning_verification(
        project_id: str,
        request: CommissioningVerificationRequest,
        session: AuthenticatedSession,
        *,
        required_kind: VerificationKind | None = None,
    ) -> CommissioningVerification:
        require_project(project_id)
        actor = require_authority(project_id, session)
        require_device(project_id, request.device_id)
        if required_kind is not None and request.kind is not required_kind:
            raise HTTPException(
                status_code=409, detail=f"{required_kind.value} verification required"
            )
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            verified_at = totp.verify(request.totp_code)
            record = CommissioningVerification(
                verification_id=f"verification-{uuid4()}",
                project_id=project_id,
                device_id=request.device_id,
                kind=request.kind,
                outcome=request.outcome,
                rationale=request.rationale,
                evidence_reference=request.evidence_reference,
                connection_id=request.connection_id,
                control_surface_id=request.control_surface_id,
                manifest_id=request.manifest_id,
                label_id=request.label_id,
                label_endpoint=request.label_endpoint,
                verified_by_actor_id=actor.actor_id,
                verified_at=verified_at,
            )
            commissioning_store.record_verification(record)
            return record
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/v1/projects/{project_id}/commissioning/verifications",
        response_model=CommissioningVerification,
        status_code=201,
    )
    def create_commissioning_verification(
        project_id: str,
        request: CommissioningVerificationRequest,
        session: AuthenticatedSession = required_session,
    ) -> CommissioningVerification:
        return record_commissioning_verification(project_id, request, session)

    @app.post(
        "/v1/projects/{project_id}/commissioning/label-verifications",
        response_model=CommissioningVerification,
        status_code=201,
    )
    def create_label_verification(
        project_id: str,
        request: CommissioningVerificationRequest,
        session: AuthenticatedSession = required_session,
    ) -> CommissioningVerification:
        return record_commissioning_verification(
            project_id, request, session, required_kind=VerificationKind.LABEL
        )

    @app.post(
        "/v1/projects/{project_id}/commissioning/failure-mode-dispositions",
        response_model=FailureModeDisposition,
        status_code=201,
    )
    def create_failure_mode_disposition(
        project_id: str,
        request: FailureModeDispositionRequest,
        session: AuthenticatedSession = required_session,
    ) -> FailureModeDisposition:
        require_project(project_id)
        actor = require_authority(project_id, session)
        require_device(project_id, request.device_id)
        if totp is None:
            raise HTTPException(status_code=503, detail="authenticator state unavailable")
        try:
            decided_at = totp.verify(request.totp_code)
            record = FailureModeDisposition(
                disposition_id=f"disposition-{uuid4()}",
                project_id=project_id,
                device_id=request.device_id,
                failure_mode_id=request.failure_mode_id,
                disposition=request.disposition,
                rationale=request.rationale,
                evidence_reference=request.evidence_reference,
                decided_by_actor_id=actor.actor_id,
                decided_at=decided_at,
            )
            commissioning_store.record_disposition(record)
            return record
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
