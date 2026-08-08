"""FastAPI health, status, findings, and bounded-label metrics."""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from hashlib import sha256
from html import escape
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from reefproof import __version__
from reefproof.api.database_explorer import register_database_explorer_routes
from reefproof.api.operations import (
    HostedOperations,
    LocalHostedOperations,
    register_hosted_operation_routes,
)
from reefproof.api.projects import register_project_routes
from reefproof.api.sessions import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    ActiveSession,
    AuthenticatedSession,
    OperatorSessions,
    SessionDependencies,
)
from reefproof.api.workbench import (
    ReturnFlowPolicyInputs,
    ReturnFlowPolicyPreview,
    ReturnFlowPolicyRevision,
    ReturnFlowPolicyTemplate,
    preview_flow,
)
from reefproof.auth_totp import TotpState
from reefproof.invariants import registered_invariant_ids
from reefproof.physical import PhysicalTwin, mock_collective_physical_twin
from reefproof.project_state import PROJECT_ID
from reefproof.project_store import ProjectStore
from reefproof.rules import InvariantCatalog, invariant_catalog
from reefproof.service import AssuranceReadiness, RuntimeState, evaluate_readiness
from reefproof.storage import Database
from reefproof.storage.explorer import SQLiteExplorer


class WorkbenchRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_mode: str
    hydros_connection: str
    mqtt_connection: str
    last_valid_configuration_at: str | None = None
    last_configuration_change_at: str | None = None
    configuration_hash: str | None = None
    policy_hash: str | None = None
    annotation_hash: str | None = None
    alert_delivery_state: str
    monitoring_confidence: str
    readiness: str
    reasons: tuple[str, ...] = ()
    active_findings: dict[str, int] = {}


class WorkbenchStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    runtime: WorkbenchRuntimeState


class WorkbenchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    href: str
    available: bool = True


class ElectricalPostureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    import_state: str
    headline: str
    recommended_action: WorkbenchAction
    captured_at: str | None = None
    configuration_hash: str | None = None
    snapshot_hash: str | None = None
    observed_entity_count: int = 0
    entity_counts: dict[str, int] = Field(default_factory=dict)
    unknown_entity_count: int = 0
    redacted_field_count: int = 0
    redaction_categories: dict[str, int] = Field(default_factory=dict)
    unproven_domains: tuple[str, ...] = ()


class WorkbenchSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bootstrap_secret: str | None = Field(default=None, json_schema_extra={"writeOnly": True})
    totp_code: str | None = Field(default=None, json_schema_extra={"writeOnly": True})


_WORKBENCH_PAGES = (
    ("overview", "Overview", "/workbench"),
    ("system-map", "System Map", "/workbench/system-map"),
    ("assurance", "Assurance", "/workbench/assurance"),
    ("evidence", "Evidence", "/workbench/evidence"),
    ("sessions", "Sessions", "/workbench/sessions"),
    ("database", "Database", "/workbench/database"),
)

_OPERATOR_LOG = logging.getLogger("uvicorn.error")


def _log_operator_event(event_name: str, **fields: object) -> None:
    serialized_fields = " ".join(f"{key}={value}" for key, value in fields.items())
    message = f"{event_name} {serialized_fields}" if serialized_fields else event_name
    _OPERATOR_LOG.info(message)


class _DatabaseOperatorSessionStore:
    def __init__(
        self,
        *,
        database: Database,
        project_id: str,
        now: Callable[[], datetime],
    ) -> None:
        self._database = database
        self._project_id = project_id
        self._now = now

    def record_session(
        self,
        session_id: str,
        principal_id: str,
        issued_at: int,
        authentication_generation: int,
    ) -> None:
        self._database.record_operator_session(
            project_id=self._project_id,
            session_id=session_id,
            principal_id=principal_id,
            issued_at=issued_at,
            authentication_generation=authentication_generation,
        )

    def has_session(
        self,
        session_id: str,
        principal_id: str,
        authentication_generation: int,
    ) -> bool:
        return self._database.operator_session_exists(
            project_id=self._project_id,
            session_id=session_id,
            principal_id=principal_id,
            authentication_generation=authentication_generation,
        )

    def revoke_session(self, session_id: str) -> bool:
        return self._database.revoke_operator_session(
            project_id=self._project_id,
            session_id=session_id,
            revoked_at=self._now(),
        )

    def list_sessions(
        self,
        principal_id: str,
        authentication_generation: int,
    ) -> tuple[ActiveSession, ...]:
        rows = self._database.list_active_operator_sessions(
            project_id=self._project_id,
            principal_id=principal_id,
            authentication_generation=authentication_generation,
        )
        return tuple(
            ActiveSession(
                session_id=row.session_id,
                principal_id=row.principal_id,
                issued_at=row.issued_at,
            )
            for row in rows
        )


def create_app(
    *,
    runtime_state: Callable[[], RuntimeState],
    database: Database,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    bootstrap_secret: str | None = None,
    acceptance_principal_id: str = "local-acceptance-authority",
    acceptance_principal_display_name: str = "Local acceptance authority",
    project_store: ProjectStore | None = None,
    active_project_id: str = PROJECT_ID,
    totp_path: Path | None = None,
    hosted_operations: HostedOperations | None = None,
    session_https_only: bool = False,
) -> FastAPI:
    """Create one dependency-explicit local API application."""

    app = FastAPI(
        title="ReefProof",
        version=__version__,
        description=(
            "Local configuration assurance for living systems. ReefProof observes, "
            "models, challenges, and alerts; HYDROS remains runtime authority."
        ),
        openapi_tags=[
            {"name": "Workbench", "description": "Manual, local workbench contracts."},
            {"name": "Projects", "description": "Authenticated project evidence and review."},
            {"name": "Database", "description": "Authenticated, query-only SQLite explorer."},
            {"name": "Operations", "description": "Local health, status, findings, and metrics."},
        ],
        docs_url=None,
        redoc_url=None,
        openapi_url="/v1/openapi.json",
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_urlsafe(48),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE_SECONDS,
        same_site="strict",
        https_only=session_https_only,
    )
    totp = TotpState(
        totp_path or database.path.parent / "operator-totp.json",
        principal_id=acceptance_principal_id,
        now=now,
    )
    operator_sessions = OperatorSessions(
        bootstrap_secret,
        principal_id=acceptance_principal_id,
        principal_display_name=acceptance_principal_display_name,
        now=now,
        authentication_generation=lambda: totp.authentication_generation,
        session_store=_DatabaseOperatorSessionStore(
            database=database,
            project_id=active_project_id,
            now=now,
        ),
    )
    session_dependencies = SessionDependencies(operator_sessions)
    required_session = Depends(session_dependencies.required)
    project_store = project_store or ProjectStore(database.path)
    request_observations: dict[tuple[str, str, str, str], int] = defaultdict(int)
    physical_twin = mock_collective_physical_twin()
    web_root = Path(__file__).parent / "web"
    static_root = web_root / "static"
    templates = Jinja2Templates(directory=web_root / "templates")
    asset_paths = (
        static_root / "workbench.css",
        static_root / "workbench-pages.css",
        static_root / "workbench.js",
        static_root / "icon.png",
        static_root / "logo-v0.1.png",
        static_root / "favicon.svg",
        static_root / "favicon.ico",
    )
    asset_version = sha256(
        b"".join(
            path.read_bytes() if path.exists() else f"MISSING:{path.name}".encode()
            for path in asset_paths
        )
    ).hexdigest()[:12]
    app.mount("/assets", StaticFiles(directory=static_root), name="assets")
    register_project_routes(
        app,
        store=project_store,
        operator_sessions=operator_sessions,
        session_dependencies=session_dependencies,
        now=now,
        totp=totp,
        active_project_id=active_project_id,
    )
    register_database_explorer_routes(
        app,
        explorer=SQLiteExplorer(database.path),
        operator_sessions=operator_sessions,
        session_dependencies=session_dependencies,
    )

    def audit_hosted_operation(event_name: str, **fields: object) -> None:
        _log_operator_event(event_name, **fields)

    register_hosted_operation_routes(
        app,
        operations=hosted_operations
        or LocalHostedOperations(
            database=database,
            data_directory=database.path.parent,
            backup_directory=None,
            now=now,
        ),
        operator_sessions=operator_sessions,
        session_dependencies=session_dependencies,
        audit=audit_hosted_operation,
    )

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        started = time.monotonic()
        failed_exception = False
        try:
            response = await call_next(request)
        except Exception:
            failed_exception = True
            _OPERATOR_LOG.error("api.request_failed request_id=%s", request_id)
            response = JSONResponse(
                content={"detail": "internal server error"},
                status_code=500,
            )
        route = request.scope.get("route")
        route_name = str(getattr(route, "path", "unmatched"))
        status_class = f"{response.status_code // 100}xx"
        duration_ms = min(60_000, round((time.monotonic() - started) * 1_000, 3))
        _OPERATOR_LOG.info(
            "api.request route=%s method=%s request_id=%s status_class=%s duration_ms=%s",
            route_name,
            request.method,
            request_id,
            status_class,
            duration_ms,
        )
        policy_preview = (request.method, route_name) == (
            "POST",
            "/v1/workbench/policy-preview",
        )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not policy_preview:
            session = operator_sessions.resolve(request.session.get("session_id"))
            principal_id = session.principal.principal_id if session is not None else "anonymous"
            outcome = (
                "failed"
                if failed_exception
                else ("success" if response.status_code < 400 else "rejected")
            )
            database.record_api_mutation(
                request_id=request_id,
                route_name=route_name,
                method=request.method,
                principal_id=principal_id,
                target_type=None,
                target_id=None,
                outcome=outcome,
                status_code=response.status_code,
                occurred_at=now(),
            )
        else:
            outcome = "failed" if failed_exception else "read"
        request_observations[(route_name, request.method, status_class, outcome)] += 1
        response.headers["X-ReefProof-Request-ID"] = request_id
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            ("default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'"),
        )
        return response

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(static_root / "favicon.ico")

    @app.get("/v1/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_reference() -> HTMLResponse:
        document = escape(json.dumps(app.openapi(), indent=2, sort_keys=True))
        return HTMLResponse(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>ReefProof v1 API reference</title>"
            "<style>body{font:14px system-ui;margin:2rem;max-width:100ch}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head>"
            f"<body><h1>ReefProof v1 API reference</h1><pre>{document}</pre></body></html>"
        )

    def render_workbench_page(request: Request, page: str) -> Response:
        page_label = next(label for slug, label, _route in _WORKBENCH_PAGES if slug == page)
        return templates.TemplateResponse(
            request=request,
            name="workbench.html",
            context={
                "asset_version": asset_version,
                "navigation": _WORKBENCH_PAGES,
                "page": page,
                "page_label": page_label,
                "active_project_id": active_project_id,
            },
        )

    @app.get("/workbench", response_class=HTMLResponse)
    def workbench(request: Request) -> Response:
        return render_workbench_page(request, "overview")

    @app.get("/workbench/system-map", response_class=HTMLResponse)
    def workbench_system_map(request: Request) -> Response:
        return render_workbench_page(request, "system-map")

    @app.get("/workbench/assurance", response_class=HTMLResponse)
    def workbench_assurance(request: Request) -> Response:
        return render_workbench_page(request, "assurance")

    @app.get("/workbench/evidence", response_class=HTMLResponse)
    def workbench_evidence(request: Request) -> Response:
        return render_workbench_page(request, "evidence")

    @app.get("/workbench/sessions", response_class=HTMLResponse)
    def workbench_sessions(request: Request) -> Response:
        return render_workbench_page(request, "sessions")

    @app.get("/workbench/database", response_class=HTMLResponse)
    def workbench_database(request: Request) -> Response:
        return render_workbench_page(request, "database")

    def workbench_state() -> WorkbenchStateResponse:
        state = runtime_state()
        report = evaluate_readiness(state, now=now())
        counts = database.active_finding_counts()
        active_findings = {
            f"{severity.value}:{finding_state.value}": count
            for (severity, finding_state), count in counts.items()
        }
        return WorkbenchStateResponse(
            project_id=active_project_id,
            runtime=WorkbenchRuntimeState(
                operating_mode=state.operating_mode,
                hydros_connection=state.hydros_connection.value,
                mqtt_connection=state.mqtt_connection.value,
                last_valid_configuration_at=(
                    state.last_valid_configuration_at.isoformat()
                    if state.last_valid_configuration_at
                    else None
                ),
                last_configuration_change_at=(
                    state.last_configuration_change_at.isoformat()
                    if state.last_configuration_change_at
                    else None
                ),
                configuration_hash=state.configuration_hash,
                policy_hash=state.policy_hash,
                annotation_hash=state.annotation_hash,
                alert_delivery_state=state.alert_delivery_state.value,
                monitoring_confidence=report.monitoring_confidence.value,
                readiness=report.readiness.value,
                reasons=tuple(report.reasons),
                active_findings=active_findings,
            ),
        )

    @app.get("/v1/workbench/actions", response_model=list[WorkbenchAction])
    def workbench_actions() -> list[WorkbenchAction]:
        return [
            WorkbenchAction(
                id="author_assurance",
                label="Author the return-flow policy",
                description=(
                    "Create a deterministic assurance revision using bounded manual evidence."
                ),
                href="/workbench/assurance",
            ),
            WorkbenchAction(
                id="inspect_evidence",
                label="Inspect committed evidence",
                description="Inspect immutable evidence, trust state, and executable invariants.",
                href="/workbench/evidence",
            ),
            WorkbenchAction(
                id="review_system_map",
                label="Review the physical model",
                description="Inspect the authored return-path model and example findings.",
                href="/workbench/system-map",
            ),
        ]

    @app.get(
        "/v1/workbench/electrical-posture",
        response_model=ElectricalPostureResponse,
    )
    def electrical_posture() -> ElectricalPostureResponse:
        snapshot = database.latest_snapshot()
        action = WorkbenchAction(
            id="review_unproven_electrical_mappings",
            label="Review unproven electrical mappings",
            description=(
                "Inspect which circuit, protection, backup-power, equipment, and function "
                "mappings are not yet proven."
            ),
            href="/workbench/system-map",
        )
        if snapshot is None:
            return ElectricalPostureResponse(
                project_id=active_project_id,
                import_state="empty",
                headline="No electrical configuration has been imported.",
                recommended_action=action,
                unproven_domains=(
                    "controller topology",
                    "circuit protection",
                    "backup power",
                    "electrical mappings",
                ),
            )

        entity_counts: dict[str, int] = {}
        for entity in snapshot.entities:
            key = entity.entity_type.value
            entity_counts[key] = entity_counts.get(key, 0) + 1
        manifest = snapshot.vendor_extensions.get("redaction_manifest", {})
        redacted_field_count = 0
        redaction_categories: dict[str, int] = {}
        if isinstance(manifest, dict):
            count = manifest.get("redacted_field_count")
            if isinstance(count, int) and not isinstance(count, bool):
                redacted_field_count = count
            categories = manifest.get("categories")
            if isinstance(categories, dict):
                redaction_categories = {
                    str(key): value
                    for key, value in categories.items()
                    if isinstance(value, int) and not isinstance(value, bool)
                }
        return ElectricalPostureResponse(
            project_id=active_project_id,
            import_state="partial",
            headline=(
                "Partial electrical configuration imported. Circuit protection, backup power, "
                "and authored electrical mappings are not yet proven."
            ),
            recommended_action=action,
            captured_at=snapshot.captured_at.isoformat(),
            configuration_hash=snapshot.configuration_hash,
            snapshot_hash=snapshot.snapshot_hash,
            observed_entity_count=len(snapshot.entities),
            entity_counts=dict(sorted(entity_counts.items())),
            unknown_entity_count=sum(
                entity.confidence.value == "unknown" for entity in snapshot.entities
            ),
            redacted_field_count=redacted_field_count,
            redaction_categories=dict(sorted(redaction_categories.items())),
            unproven_domains=(
                "display heating",
                "primary returns",
                "circuit protection",
                "backup power",
                "authored electrical mappings",
            ),
        )

    @app.get("/v1/workbench/policy-template", response_model=ReturnFlowPolicyTemplate)
    def flow_template() -> ReturnFlowPolicyTemplate:
        return ReturnFlowPolicyTemplate()

    @app.get("/v1/workbench/invariant-catalog", response_model=InvariantCatalog)
    def get_invariant_catalog() -> InvariantCatalog:
        return invariant_catalog()

    @app.get("/v1/workbench/physical-twin", response_model=PhysicalTwin)
    def get_physical_twin() -> PhysicalTwin:
        return physical_twin

    @app.post("/v1/workbench/policy-preview", response_model=ReturnFlowPolicyPreview)
    def flow_preview(request: ReturnFlowPolicyInputs) -> ReturnFlowPolicyPreview:
        return preview_flow(request)

    @app.get("/v1/workbench/auth-method", response_model=dict[str, str])
    def get_auth_method() -> dict[str, str]:
        """Return the required authentication method without requiring authentication.

        This allows the frontend to auto-select the correct credential method
        (bootstrap secret or TOTP) based on enrollment status.
        """
        method = "totp" if totp.enrolled else "bootstrap"
        return {"method": method}

    @app.post(
        "/v1/workbench/operator-sessions",
        status_code=201,
    )
    def create_operator_session(
        request: WorkbenchSessionRequest,
        response: Response,
        http_request: Request,
    ) -> dict[str, str]:
        if totp.enrolled:
            code = (request.totp_code or "").strip()
            if code == "":
                _log_operator_event(
                    "operator.session_establish_failed", method="totp", reason="missing_code"
                )
                raise HTTPException(status_code=401, detail="valid authenticator code required")
            try:
                totp.verify(code)
            except ValueError as error:
                _log_operator_event(
                    "operator.session_establish_failed", method="totp", reason="invalid_code"
                )
                raise HTTPException(status_code=401, detail=str(error)) from error
            session_id = operator_sessions.create_authenticated()
            method = "totp"
        else:
            if not operator_sessions.configured:
                _log_operator_event(
                    "operator.session_establish_failed",
                    method="bootstrap_secret",
                    reason="bootstrap_secret_not_configured",
                )
                raise HTTPException(
                    status_code=503,
                    detail="bootstrap shared secret is not configured",
                )
            bootstrap_secret = (request.bootstrap_secret or "").strip()
            session_id = operator_sessions.create(bootstrap_secret)
            if session_id is None:
                _log_operator_event(
                    "operator.session_establish_failed",
                    method="bootstrap_secret",
                    reason="invalid_bootstrap_secret",
                )
                raise HTTPException(status_code=401, detail="invalid bootstrap shared secret")
            method = "bootstrap_secret"
        principal = operator_sessions.principal(session_id)
        if principal is None:
            _log_operator_event(
                "operator.session_establish_failed",
                method="totp" if totp.enrolled else "bootstrap_secret",
                reason="session_creation_failed",
            )
            raise HTTPException(status_code=401, detail="session establishment failed")
        _log_operator_event(
            "operator.session_established",
            method=method,
            principal_id=principal.principal_id,
        )
        http_request.session["session_id"] = session_id
        return {
            "principal_id": principal.principal_id,
            "principal_display_name": principal.display_name,
        }

    @app.post("/v1/workbench/operator-sessions/current/revocations", status_code=204)
    def logout_operator_session(
        request: Request,
        response: Response,
    ) -> Response:
        session_id = request.session.get("session_id")
        principal = operator_sessions.principal(session_id)
        operator_sessions.revoke(session_id)
        request.session.clear()
        _log_operator_event(
            "operator.session_revoked",
            principal_id=principal.principal_id if principal is not None else "anonymous",
        )
        response.status_code = 204
        return response

    @app.get("/v1/workbench/totp", response_model=dict[str, bool])
    def totp_status(
        _session: AuthenticatedSession = required_session,
    ) -> dict[str, bool]:
        return {"enrolled": totp.enrolled}

    @app.post("/v1/workbench/totp/enrollment", status_code=201)
    def begin_totp_enrollment(
        response: Response,
        session: AuthenticatedSession = required_session,
    ) -> dict[str, str]:
        principal = session.principal
        try:
            challenge_id, qr_png_base64 = totp.enrollment()
        except ValueError as error:
            _log_operator_event(
                "operator.totp_enrollment_rejected",
                principal_id=principal.principal_id,
                reason="already_enrolled",
            )
            raise HTTPException(status_code=409, detail=str(error)) from error
        _log_operator_event(
            "operator.totp_enrollment_started",
            principal_id=principal.principal_id,
            challenge_id=challenge_id,
        )
        response.headers["Cache-Control"] = "no-store"
        return {"challenge_id": challenge_id, "qr_png_base64": qr_png_base64}

    @app.post("/v1/workbench/totp/enrollment/confirm", status_code=204)
    def confirm_totp_enrollment(
        request: dict[str, str],
        response: Response,
        session: AuthenticatedSession = required_session,
    ) -> Response:
        principal = session.principal
        try:
            totp.confirm(request.get("challenge_id", ""), request.get("totp_code", ""))
        except ValueError as error:
            _log_operator_event(
                "operator.totp_enrollment_confirm_failed",
                principal_id=principal.principal_id,
                reason="invalid_challenge_or_code",
            )
            raise HTTPException(status_code=409, detail=str(error)) from error
        _log_operator_event(
            "operator.totp_enrollment_confirmed",
            principal_id=principal.principal_id,
        )
        response.headers["Cache-Control"] = "no-store"
        response.status_code = 204
        return response

    @app.post(
        "/v1/workbench/policy-revisions",
        response_model=ReturnFlowPolicyRevision,
        status_code=201,
    )
    def create_flow_revision(
        request: ReturnFlowPolicyInputs,
        session: AuthenticatedSession = required_session,
    ) -> ReturnFlowPolicyRevision:
        return database.record_return_flow_policy_revision(
            request,
            created_at=now(),
            authoring_operator_session_id=session.session_id,
        )

    @app.get(
        "/v1/workbench/policy-revisions/latest",
        response_model=ReturnFlowPolicyRevision | None,
    )
    def latest_flow_revision() -> ReturnFlowPolicyRevision | None:
        return database.latest_return_flow_policy_revision()

    @app.get("/v1/system/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/v1/system/health/ready")
    def health_ready() -> Response:
        report = evaluate_readiness(runtime_state(), now=now())
        status_code = 503 if report.readiness is AssuranceReadiness.UNREADY else 200
        return JSONResponse(
            content=report.model_dump(mode="json"),
            status_code=status_code,
        )

    @app.get("/v1/system/status")
    def status() -> dict[str, object]:
        state = runtime_state()
        report = evaluate_readiness(state, now=now())
        counts = database.active_finding_counts()
        active_findings = {
            f"{severity.value}:{finding_state.value}": count
            for (severity, finding_state), count in counts.items()
        }
        workbench = workbench_state()
        return {
            "version": __version__,
            "project_id": active_project_id,
            "runtime": workbench.runtime.model_dump(mode="json"),
            "uptime_seconds": max(0.0, (now() - state.started_at).total_seconds()),
            "operating_mode": state.operating_mode,
            "hydros_connection": state.hydros_connection.value,
            "mqtt_connection": state.mqtt_connection.value,
            "last_valid_configuration_at": (
                state.last_valid_configuration_at.isoformat()
                if state.last_valid_configuration_at
                else None
            ),
            "last_configuration_change_at": (
                state.last_configuration_change_at.isoformat()
                if state.last_configuration_change_at
                else None
            ),
            "configuration_hash": state.configuration_hash,
            "last_evaluation_at": (
                state.last_evaluation_at.isoformat() if state.last_evaluation_at else None
            ),
            "last_evaluation_duration_seconds": state.last_evaluation_duration_seconds,
            "policy_hash": state.policy_hash,
            "annotation_hash": state.annotation_hash,
            "alert_delivery_state": state.alert_delivery_state.value,
            "monitoring_confidence": report.monitoring_confidence.value,
            "readiness": report.readiness.value,
            "reasons": report.reasons,
            "active_findings": active_findings,
        }

    @app.get("/v1/findings")
    def findings() -> list[dict[str, object]]:
        return [finding.model_dump(mode="json") for finding in database.active_findings()]

    @app.get("/v1/findings/{invariant_id}")
    def finding(invariant_id: str) -> dict[str, object]:
        active = database.active_finding(invariant_id)
        if active is None:
            raise HTTPException(status_code=404, detail="finding not found")
        return active.model_dump(mode="json")

    @app.get("/v1/system/metrics")
    def metrics() -> Response:
        state = runtime_state()
        current_time = now()
        registry = CollectorRegistry()
        Gauge("reefproof_up", "Whether the ReefProof process is up.", registry=registry).set(1)
        Gauge(
            "reefproof_hydros_connected",
            "Whether the HYDROS transport is connected.",
            registry=registry,
        ).set(state.hydros_connection.value == "connected")
        Gauge(
            "reefproof_mqtt_connected",
            "Whether the approved MQTT response stream is connected.",
            registry=registry,
        ).set(state.mqtt_connection.value == "connected")
        timestamp_metrics = (
            (
                "reefproof_last_config_fetch_timestamp_seconds",
                "Unix timestamp of the latest valid configuration observation.",
                state.last_valid_configuration_at,
            ),
            (
                "reefproof_last_config_change_timestamp_seconds",
                "Unix timestamp of the latest observed configuration change.",
                state.last_configuration_change_at,
            ),
            (
                "reefproof_last_evaluation_timestamp_seconds",
                "Unix timestamp of the latest completed policy evaluation.",
                state.last_evaluation_at,
            ),
        )
        for metric_name, description, timestamp in timestamp_metrics:
            metric = Gauge(metric_name, description, registry=registry)
            if timestamp is not None:
                metric.set(timestamp.timestamp())
        config_age = Gauge(
            "reefproof_config_age_seconds",
            "Age of the latest valid configuration.",
            registry=registry,
        )
        if state.last_valid_configuration_at is not None:
            config_age.set(
                max(0.0, (current_time - state.last_valid_configuration_at).total_seconds())
            )
        evaluation_duration = Gauge(
            "reefproof_evaluation_duration_seconds",
            "Duration of the latest completed policy evaluation.",
            registry=registry,
        )
        if state.last_evaluation_duration_seconds is not None:
            evaluation_duration.set(state.last_evaluation_duration_seconds)
        active = Gauge(
            "reefproof_active_findings",
            "Current active findings by bounded severity and state.",
            labelnames=("severity", "state"),
            registry=registry,
        )
        for (severity, finding_state), count in database.active_finding_counts().items():
            active.labels(severity=severity.value, state=finding_state.value).set(count)
        api_requests = Counter(
            "reefproof_api_requests",
            "API requests by bounded route template, method, status class, and outcome.",
            labelnames=("route", "method", "status_class", "outcome"),
            registry=registry,
        )
        for labels, count in request_observations.items():
            api_requests.labels(*labels).inc(count)
        invariant_results = Counter(
            "reefproof_invariant_results",
            "Durable built-in invariant results by bounded dimensions.",
            labelnames=("invariant_id", "severity", "state"),
            registry=registry,
        )
        known_invariants = registered_invariant_ids()
        for (
            result_state,
            severity,
            invariant_id,
        ), count in database.invariant_result_counts().items():
            if invariant_id not in known_invariants:
                continue
            invariant_results.labels(
                invariant_id=invariant_id,
                severity=severity.value,
                state=result_state.value,
            ).inc(count)
        build_info = Gauge(
            "reefproof_build_info",
            "ReefProof build identity.",
            labelnames=("version", "commit"),
            registry=registry,
        )
        build_info.labels(
            version=__version__,
            commit=os.environ.get("REEFPROOF_COMMIT", "unknown"),
        ).set(1)
        alert_attempts = Counter(
            "reefproof_alert_attempts",
            "Durable alert delivery attempts by bounded adapter and result.",
            labelnames=("adapter", "result"),
            registry=registry,
        )
        alert_duration = Gauge(
            "reefproof_alert_delivery_duration_seconds",
            "Mean durable alert delivery duration by bounded adapter and result.",
            labelnames=("adapter", "result"),
            registry=registry,
        )
        errors = Counter(
            "reefproof_errors",
            "Durable ReefProof errors by bounded component and category.",
            labelnames=("component", "category"),
            registry=registry,
        )
        known_adapters = {"console", "home_assistant"}
        for (adapter, result), (count, mean_duration) in database.alert_attempt_metrics().items():
            if adapter not in known_adapters:
                continue
            alert_attempts.labels(adapter=adapter, result=result.value).inc(count)
            alert_duration.labels(adapter=adapter, result=result.value).set(mean_duration)
            if result.value == "failure":
                errors.labels(component="alerting", category="alert_delivery").inc(count)
        return Response(
            content=generate_latest(registry),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    def openapi() -> dict[str, object]:
        """Expose the enforced browser auth boundary in the generated contract."""

        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        authorization_overrides = {
            ("/v1/workbench/operator-sessions", "post"): "session establishment",
            ("/v1/workbench/operator-sessions/current/revocations", "post"): (
                "idempotent current-session revocation"
            ),
            ("/v1/projects/{project_id}/trust/revocations", "post"): ("acceptanceAuthority"),
            ("/v1/projects/{project_id}/trust/restorations", "post"): ("acceptanceAuthority"),
            ("/v1/projects/{project_id}/candidates/{candidate_fact_id}/review", "post"): (
                "acceptanceAuthority"
            ),
            ("/v1/operations/diagnostics", "get"): "hostedDesktopOperation",
            ("/v1/operations/backups", "post"): "hostedDesktopOperation",
            ("/v1/operations/backups/{backup_id}/download", "post"): ("hostedDesktopOperation"),
            ("/v1/operations/restart", "post"): "hostedDesktopOperation",
        }
        persistence_audit_overrides = {
            ("/v1/workbench/policy-preview", "post"): ("non-persisting evaluation; no audit"),
            ("/v1/workbench/policy-revisions", "post"): (
                "audit; immutable policy revision on success"
            ),
            ("/v1/workbench/operator-sessions", "post"): ("audit; operator session on success"),
            ("/v1/workbench/operator-sessions/current/revocations", "post"): (
                "audit; revoke valid current session if present"
            ),
            ("/v1/workbench/totp/enrollment", "post"): (
                "audit; pending authenticator state on success"
            ),
            ("/v1/workbench/totp/enrollment/confirm", "post"): (
                "audit; confirmed authenticator state on success"
            ),
            ("/v1/projects/{project_id}/trust/revocations", "post"): (
                "audit; immutable trust event on success"
            ),
            ("/v1/projects/{project_id}/trust/restorations", "post"): (
                "audit; immutable trust event on success"
            ),
            ("/v1/projects/{project_id}/candidates/{candidate_fact_id}/review", "post"): (
                "audit; decision/domain event on success"
            ),
            ("/v1/database/schema", "get"): "query-only; none",
            ("/v1/database/tables/{table_name}", "get"): "query-only; none",
            ("/v1/operations/backups", "post"): "audit; staged backup on success",
            ("/v1/operations/backups/{backup_id}/download", "post"): (
                "audit; one-time claim on success"
            ),
            ("/v1/operations/restart", "post"): ("audit; supervisor request on success"),
        }
        for path, operations in schema["paths"].items():
            if path.startswith("/v1/projects"):
                tag = "Projects"
            elif path.startswith("/v1/database"):
                tag = "Database"
            elif path.startswith("/v1/workbench"):
                tag = "Workbench"
            else:
                tag = "Operations"
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                operation["tags"] = [tag]
                default_authorization = "operatorSession" if operation.get("security") else "public"
                operation["x-reefproof-authorization"] = authorization_overrides.get(
                    (path, method), default_authorization
                )
                operation["x-reefproof-persistence-audit"] = persistence_audit_overrides.get(
                    (path, method), "none"
                )
                success_statuses = sorted(
                    status
                    for status in operation.get("responses", {})
                    if str(status).startswith("2")
                )
                if success_statuses:
                    operation["x-reefproof-success-status"] = success_statuses[0]
            if (
                path
                in {
                    "/v1/workbench/operator-sessions",
                    "/v1/workbench/operator-sessions/current/revocations",
                }
                and "post" in operations
            ):
                operations["post"]["security"] = []
        app.openapi_schema = schema
        return schema

    app.openapi = openapi

    return app
