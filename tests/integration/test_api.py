from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from typer.testing import CliRunner

from reefproof.api import create_app
from reefproof.cli import app as cli_app
from reefproof.invariants import (
    EvaluationRun,
    InvariantResult,
    InvariantState,
    Severity,
    registered_invariant_ids,
)
from reefproof.service import RuntimeState, import_hydros_export
from reefproof.storage import AlertAttempt, AlertAttemptResult, Database

NOW = datetime.fromisoformat("2026-07-25T22:30:00-04:00")
HASH = f"sha256:{'e' * 64}"
RUN_ID = "62345678-abcd-4234-8234-123456789abc"
cli_runner = CliRunner()
SECRET_FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-secret-bearing.json")
ADR_0008 = Path("docs/adr/0008-versioned-api-and-terminology-contract.md")
PRESENTATION_ROUTES = {
    "/assets",
    "/favicon.ico",
    "/workbench",
    "/workbench/system-map",
    "/workbench/assurance",
    "/workbench/evidence",
    "/workbench/sessions",
    "/workbench/database",
}


@dataclass(frozen=True)
class _AdrOperation:
    authentication: str
    authorization: str
    persistence_audit: str
    success_status: str


def _adr_0008_operations() -> dict[tuple[str, str], _AdrOperation]:
    operations: dict[tuple[str, str], _AdrOperation] = {}
    for line in ADR_0008.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `/v1/"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        assert len(cells) == 6, f"malformed ADR 0008 route row: {line}"
        path, method, authentication, authorization, persistence_audit, status = cells
        key = (path, method)
        assert key not in operations, f"duplicate ADR 0008 route row: {method} {path}"
        operations[key] = _AdrOperation(
            authentication=authentication,
            authorization=authorization,
            persistence_audit=persistence_audit,
            success_status=status,
        )
    assert operations, "ADR 0008 contains no executable route matrix"
    return operations


class _AppClient:
    def __init__(self, app: FastAPI) -> None:
        self.runner = asyncio.Runner()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    def get(self, path: str) -> httpx.Response:
        return self.runner.run(self.client.get(path))

    def post(
        self,
        path: str,
        payload: dict[str, object],
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        return self.runner.run(self.client.post(path, json=payload, headers=headers))

    def request(
        self, method: str, path: str, *, json: dict[str, object] | None = None
    ) -> httpx.Response:
        return self.runner.run(self.client.request(method, path, json=json))

    def close(self) -> None:
        self.runner.run(self.client.aclose())
        self.runner.close()


_APP_CLIENTS: dict[FastAPI, _AppClient] = {}


@pytest.fixture(autouse=True)
def close_app_clients() -> Iterator[None]:
    yield
    for client in _APP_CLIENTS.values():
        client.close()
    _APP_CLIENTS.clear()


def _client(app: FastAPI) -> _AppClient:
    client = _APP_CLIENTS.get(app)
    if client is None:
        client = _AppClient(app)
        _APP_CLIENTS[app] = client
    return client


def _state(**changes: object) -> RuntimeState:
    values: dict[str, object] = {
        "started_at": NOW - timedelta(hours=1),
        "operating_mode": "fixture",
        "hydros_connection": "disabled",
        "mqtt_connection": "disabled",
        "last_valid_configuration_at": NOW - timedelta(seconds=30),
        "last_configuration_change_at": NOW - timedelta(minutes=5),
        "configuration_hash": HASH,
        "last_evaluation_at": NOW - timedelta(seconds=20),
        "last_evaluation_duration_seconds": 0.125,
        "latest_evaluated_configuration_hash": HASH,
        "policy_loaded": True,
        "policy_hash": HASH,
        "annotation_hash": HASH,
        "storage_writable": True,
        "unrecoverable_transport_failure": None,
        "alert_delivery_state": "healthy",
        "maximum_configuration_age_seconds": 600,
    }
    values.update(changes)
    return RuntimeState.model_validate(values)


def _database(path: Path) -> Database:
    database = Database(path)
    database.migrate()
    return database


def _get(app: FastAPI, path: str) -> httpx.Response:
    return _client(app).get(path)


def _post(
    app: FastAPI,
    path: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return _client(app).post(path, payload, headers)


def _critical_result() -> InvariantResult:
    return InvariantResult(
        invariant_id="RP-CIRC-001",
        version="1",
        severity=Severity.CRITICAL,
        state=InvariantState.FAIL,
        summary="Both returns share power.",
        detailed_explanation="Return A and Return B share MAIN-6.",
        affected_entities=("RP.DEVICE.0123456789abcdef",),
        evidence=("RP.ANNOTATION.0123456789abcdef",),
        missing_evidence=(),
        recommended_operator_action="Restore independent power.",
        evaluation_timestamp=NOW,
        configuration_hash=HASH,
        annotation_hash=HASH,
        policy_hash=HASH,
        evaluation_run_id=RUN_ID,
    )


def test_live_ready_status_and_metrics_are_locally_observable(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    app = create_app(
        runtime_state=lambda: _state(),
        database=database,
        now=lambda: NOW,
    )
    assert _get(app, "/v1/system/health/live").json() == {"status": "alive"}
    ready = _get(app, "/v1/system/health/ready")
    assert ready.status_code == 200
    assert ready.json()["readiness"] == "ready"

    status = _get(app, "/v1/system/status")
    assert status.status_code == 200
    assert status.json()["configuration_hash"] == HASH
    assert status.json()["operating_mode"] == "fixture"
    assert status.json()["last_evaluation_duration_seconds"] == 0.125
    assert status.json()["active_findings"] == {}

    metrics = _get(app, "/v1/system/metrics")
    assert metrics.status_code == 200
    assert "reefproof_up 1.0" in metrics.text
    assert "reefproof_active_findings" in metrics.text
    assert HASH not in metrics.text


def test_workbench_state_and_actions_are_exposed_from_the_server(tmp_path: Path) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )

    state = _get(app, "/v1/system/status")
    assert state.status_code == 200
    payload = state.json()
    assert payload["runtime"]["operating_mode"] == "fixture"
    assert payload["runtime"]["hydros_connection"] == "disabled"
    assert payload["runtime"]["mqtt_connection"] == "disabled"

    actions = _get(app, "/v1/workbench/actions")
    assert actions.status_code == 200
    listed = {action["id"] for action in actions.json()}
    assert {"author_assurance", "inspect_evidence", "review_system_map"} <= listed


def test_electrical_posture_exposes_safe_aggregate_evidence_only(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    import_hydros_export(
        SECRET_FIXTURE,
        captured_at=NOW,
        expected_temperature_unit="fahrenheit",
        database=database,
        evaluation_timestamp=NOW,
        evaluation_run_id="a2345678-abcd-4234-8234-123456789abc",
    )
    app = create_app(runtime_state=lambda: _state(), database=database, now=lambda: NOW)

    response = _get(app, "/v1/workbench/electrical-posture")

    assert response.status_code == 200
    assert response.json()["import_state"] == "partial"
    assert response.json()["recommended_action"]["id"] == "review_unproven_electrical_mappings"
    assert response.json()["observed_entity_count"] == 3
    assert response.json()["unknown_entity_count"] == 3
    assert response.json()["redacted_field_count"] == 13
    assert response.json()["redaction_categories"] == {
        "account_identifier": 2,
        "credential": 3,
        "device_identifier": 5,
        "network_identifier": 3,
    }
    assert "SEED-" not in response.text
    assert "192.0.2.44" not in response.text
    assert "198.51.100.17" not in response.text


def test_security_headers_and_session_responses_are_hardened(tmp_path: Path) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
        bootstrap_secret="test-operator-secret",
    )

    workbench = _get(app, "/workbench")
    assert workbench.headers["cache-control"].startswith("no-store")
    assert workbench.headers["x-content-type-options"] == "nosniff"
    assert workbench.headers["x-frame-options"] == "DENY"
    assert workbench.headers["referrer-policy"] == "no-referrer"
    assert "img-src 'self' data:" in workbench.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in workbench.headers["content-security-policy"]

    state = _get(app, "/v1/system/status")
    assert state.headers["cache-control"].startswith("no-store")

    session = _post(
        app,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "test-operator-secret"},
    )
    assert session.status_code == 201
    assert session.headers["cache-control"].startswith("no-store")


def test_openapi_describes_auth_and_groups_only_api_operations(tmp_path: Path) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )

    schema = _get(app, "/v1/openapi.json").json()
    assert schema["info"]["description"].startswith("Local configuration assurance")
    assert set(schema["components"]["securitySchemes"]) == {"operatorSession"}
    assert schema["paths"]["/v1/workbench/operator-sessions"]["post"]["security"] == []
    session_schema = schema["components"]["schemas"]["WorkbenchSessionRequest"]
    assert session_schema["properties"]["bootstrap_secret"]["writeOnly"] is True
    assert session_schema["properties"]["totp_code"]["writeOnly"] is True
    project_get = schema["paths"]["/v1/projects/{project_id}"]["get"]
    assert project_get["tags"] == ["Projects"]
    assert project_get["security"] == [{"operatorSession": []}]
    assert not any(
        parameter.get("name") == "reefproof_session"
        for parameter in project_get.get("parameters", [])
    )

    expected = _adr_0008_operations()
    observed: set[tuple[str, str]] = set()
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        methods = set(getattr(route, "methods", set()) or set())
        if path in PRESENTATION_ROUTES:
            continue
        assert path.startswith("/v1"), f"unversioned non-presentation route: {path}"
        observed.update((path, method) for method in methods)
    assert observed == set(expected)

    documented_openapi = {
        (path, method.lower())
        for path, method in expected
        if path not in {"/v1/openapi.json", "/v1/docs"} and method != "HEAD"
    }
    generated_openapi = {
        (path, method)
        for path, item in schema["paths"].items()
        if path not in PRESENTATION_ROUTES
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert generated_openapi == documented_openapi

    for (path, method), contract in expected.items():
        if method == "HEAD" or path in {"/v1/openapi.json", "/v1/docs"}:
            continue
        operation = schema["paths"][path][method.lower()]
        actual = _AdrOperation(
            authentication=("operatorSession" if operation.get("security", []) else "public"),
            authorization=operation.get("x-reefproof-authorization", ""),
            persistence_audit=operation.get("x-reefproof-persistence-audit", ""),
            success_status=operation.get("x-reefproof-success-status", ""),
        )
        assert actual == contract, f"ADR metadata mismatch for {method} {path}"
        assert contract.success_status in operation.get("responses", {})


def test_workbench_is_backend_authored_external_and_conspicuously_manual(
    tmp_path: Path,
) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )

    page = _get(app, "/workbench")
    assert page.status_code == 200
    assert "Mock Collective" in page.text
    assert "MANUAL / NOT LIVE" in page.text
    assert '<script type="module" src="/assets/workbench.js?v=' in page.text
    assert 'aria-label="Main navigation"' in page.text
    assert "Manual return-flow check" in page.text
    assert "Author one bounded return-flow policy" in page.text
    assert "Operator-export import and electrical mapping authoring are not available" in page.text
    assert '<link rel="icon" href="/assets/favicon.svg?v=' in page.text
    assert '<link rel="alternate icon" href="/favicon.ico?v=' in page.text
    assert "<script>" not in page.text
    assert 'href="/workbench/assurance"' in page.text
    assert 'href="/workbench/evidence"' in page.text

    assurance = _get(app, "/workbench/assurance")
    assert assurance.text.count("MANUAL / NOT LIVE") >= 2
    assert 'id="flow-fields"' in assurance.text

    evidence = _get(app, "/workbench/evidence")
    assert "MANUAL / NOT LIVE" in evidence.text
    assert 'id="evidence-heading"' in evidence.text
    assert 'id="rule-catalog"' in evidence.text

    system_map = _get(app, "/workbench/system-map")
    assert 'id="physical-twin"' in system_map.text
    assert 'viewBox="0 0 660 460"' in system_map.text
    assert 'id="physical-relationships"' in system_map.text
    assert 'id="physical-entities"' in system_map.text
    assert 'id="mock-findings"' in system_map.text
    stylesheet = _get(app, "/assets/workbench.css").text
    assert "@media (max-width: 36rem)" in stylesheet
    assert ".input-shell input:focus-visible" in stylesheet
    assert "min-block-size: 2.75rem" in stylesheet
    favicon = _get(app, "/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] in {
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
    assert favicon.content.startswith(b"\x00\x00\x01\x00")
    vector_favicon = _get(app, "/assets/favicon.svg")
    assert vector_favicon.status_code == 200
    assert vector_favicon.headers["content-type"] == "image/svg+xml"
    assert b"<script" not in vector_favicon.content
    assert b"#18e7ff" in vector_favicon.content
    assert b"#d7ff50" in vector_favicon.content
    logo = _get(app, "/assets/logo-v0.1.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert logo.content.startswith(b"\x89PNG\r\n\x1a\n")
    browser = _get(app, "/assets/workbench.js").text
    assert 'const API_ROOT = "/v1/workbench"' in browser
    assert '"/api/workbench' not in browser

    template = _get(app, "/v1/workbench/policy-template").json()
    assert template == {
        "schema_version": "0.1",
        "policy_template_id": "RP-POLICY-FLOW-001",
        "collective_name": "Mock Collective",
        "provenance": "MANUAL",
        "provenance_label": "MANUAL / NOT LIVE",
        "live_observation": False,
        "units": "gallons/hour",
        "fields": [
            "tank_volume_gallons",
            "pump_rated_flow_gph",
            "delivered_flow_gph",
            "minimum_turnover_per_hour",
        ],
    }

    catalog = _get(app, "/v1/workbench/invariant-catalog")
    assert catalog.status_code == 200
    catalog_document = catalog.json()
    assert catalog_document["collective_name"] == "Mock Collective"
    assert catalog_document["provenance_label"] == "MANUAL / NOT LIVE"
    assert catalog_document["live_observation"] is False
    templates = catalog_document["templates"]
    assert len(templates) == 15
    assert {template["invariant_id"] for template in templates} == set(registered_invariant_ids())
    for template in templates:
        assert template["logical_tree"]["kind"] == "rule"
        assert template["evidence_requirements"]
        assert {
            child["state"]
            for child in template["logical_tree"]["children"]
            if child["kind"] == "outcome"
        } == {"PASS", "FAIL", "UNKNOWN"}

    physical_twin = _get(app, "/v1/workbench/physical-twin")
    assert physical_twin.status_code == 200
    twin_document = physical_twin.json()
    assert twin_document["collective_name"] == "Mock Collective"
    assert twin_document["provenance_label"] == "MANUAL / NOT LIVE"
    assert twin_document["live_observation"] is False
    assert {entity["physical_type"] for entity in twin_document["entities"]} == {
        "display_tank",
        "sump",
        "return_pump",
    }
    assert {relationship["direction"] for relationship in twin_document["relationships"]} == {
        "down",
        "left",
        "up_and_right",
    }
    assert all(relationship["dependency"] for relationship in twin_document["relationships"])
    assert {
        (finding["severity"], finding["icon"], finding["state_text"])
        for finding in twin_document["findings"]
    } == {
        ("critical", "⚠", "CRITICAL"),
        ("warning", "▲", "WARNING"),
        ("info", "●", "INFO"),
    }

    for suffix in ("policy-template", "invariant-catalog", "physical-twin"):
        canonical = _get(app, f"/v1/workbench/{suffix}")
        deleted = _get(app, f"/api/workbench/{suffix}")
        assert canonical.status_code == 200
        assert deleted.status_code == 404

    schema_paths = _get(app, "/v1/openapi.json").json()["paths"]
    assert "/v1/workbench/policy-template" in schema_paths
    assert not any(path.startswith("/api/workbench") for path in schema_paths)
    assert _get(app, "/api/workbench/flow-revisions/latest").status_code == 404
    assert _post(app, "/api/workbench/session", {}).status_code == 404
    assert _post(app, "/api/workbench/policy-preview", {}).status_code == 404
    assert _post(app, "/api/workbench/flow-revisions", {}).status_code == 404


def test_flow_preview_compares_delivered_flow_only_to_operator_authored_target(
    tmp_path: Path,
) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )
    payload: dict[str, object] = {
        "tank_volume_gallons": 100,
        "pump_rated_flow_gph": 1000,
        "delivered_flow_gph": 650,
        "minimum_turnover_per_hour": 6,
    }

    passed = _post(app, "/v1/workbench/policy-preview", payload)
    assert passed.status_code == 200
    assert passed.json() == {
        "schema_version": "0.1",
        "collective_name": "Mock Collective",
        "provenance": "MANUAL",
        "provenance_label": "MANUAL / NOT LIVE",
        "live_observation": False,
        "policy_kind": "operator-authored minimum turnover",
        "state": "PASS",
        "tank_volume_gallons": 100.0,
        "pump_rated_flow_gph": 1000.0,
        "delivered_flow_gph": 650.0,
        "delivery_difference_gph": 350.0,
        "delivery_efficiency_percent": 65.0,
        "actual_turnover_per_hour": 6.5,
        "minimum_turnover_per_hour": 6.0,
        "minimum_delivered_flow_gph": 600.0,
        "explanation": (
            "The authored delivered flow meets the operator-authored minimum turnover. "
            "This preview is manual evidence, not a live HYDROS observation or a "
            "universal safety recommendation."
        ),
    }

    payload["delivered_flow_gph"] = 550
    failed = _post(app, "/v1/workbench/policy-preview", payload)
    assert failed.status_code == 200
    assert failed.json()["state"] == "FAIL"
    assert failed.json()["actual_turnover_per_hour"] == 5.5


def test_flow_preview_rejects_invalid_manual_evidence(tmp_path: Path) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )
    invalid = _post(
        app,
        "/v1/workbench/policy-preview",
        {
            "tank_volume_gallons": 100,
            "pump_rated_flow_gph": 100,
            "delivered_flow_gph": 0,
            "minimum_turnover_per_hour": 2,
        },
    )
    assert invalid.status_code == 422


def test_return_flow_policy_revisions_are_saved_and_latest_reloads_from_backend(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "reefproof.sqlite3"
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(database_path),
        now=lambda: NOW,
        bootstrap_secret="test-operator-secret",
    )
    payload: dict[str, object] = {
        "tank_volume_gallons": 250,
        "pump_rated_flow_gph": 800,
        "delivered_flow_gph": 650,
        "minimum_turnover_per_hour": 2,
    }

    unauthorized = _post(app, "/v1/workbench/policy-revisions", payload)
    assert unauthorized.status_code == 401
    session = _post(
        app,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "test-operator-secret"},
    )
    assert session.status_code == 201
    assert session.json()["principal_id"] == "local-acceptance-authority"
    set_cookie = session.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "max-age=28800" in set_cookie
    cookie = session.cookies.get("reefproof_session")
    assert cookie is not None
    assert "local-acceptance-authority" not in cookie
    revision_headers = {"Cookie": f"reefproof_session={cookie}"}

    tampered_headers = {"Cookie": f"reefproof_session={cookie}tampered"}
    assert (
        _post(app, "/v1/workbench/policy-revisions", payload, headers=tampered_headers).status_code
        == 401
    )

    latest_empty = _get(app, "/v1/workbench/policy-revisions/latest")
    assert latest_empty.status_code == 200
    assert latest_empty.json() is None
    first = _post(
        app,
        "/v1/workbench/policy-revisions",
        payload,
        headers=revision_headers,
    )
    assert first.status_code == 201
    first_document = first.json()
    assert first_document["revision_number"] == 1
    assert first_document["created_at"] == NOW.isoformat()
    assert first_document["authoring_operator_session_id"]
    assert first_document["provenance_label"] == "MANUAL / NOT LIVE"
    assert first_document["live_observation"] is False
    assert first_document["inputs"] == payload
    assert first_document["preview"]["actual_turnover_per_hour"] == 2.6

    payload["delivered_flow_gph"] = 450
    second = _post(
        app,
        "/v1/workbench/policy-revisions",
        payload,
        headers=revision_headers,
    )
    latest = _get(app, "/v1/workbench/policy-revisions/latest")
    assert second.status_code == 201
    assert second.json()["revision_number"] == 2
    assert second.json()["preview"]["state"] == "FAIL"
    assert latest.status_code == 200
    assert latest.json() == second.json()

    logout = _post(
        app,
        "/v1/workbench/operator-sessions/current/revocations",
        {},
        headers=revision_headers,
    )
    assert logout.status_code == 204
    assert (
        _post(
            app,
            "/v1/workbench/policy-revisions",
            payload,
            headers=revision_headers,
        ).status_code
        == 401
    )

    restarted = create_app(
        runtime_state=lambda: _state(),
        database=_database(database_path),
        now=lambda: NOW,
        bootstrap_secret="test-operator-secret",
    )
    assert _get(restarted, "/v1/workbench/policy-revisions/latest").json() == second.json()
    expired_session = _post(
        restarted,
        "/v1/workbench/policy-revisions",
        payload,
        headers=revision_headers,
    )
    assert expired_session.status_code == 401
    assert "test-operator-secret" not in database_path.read_bytes().decode(
        "utf-8",
        errors="ignore",
    )


def test_session_cookie_secure_attribute_is_explicitly_configurable(tmp_path: Path) -> None:
    app = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
        bootstrap_secret="test-operator-secret",
        session_https_only=True,
    )

    response = _post(
        app,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "test-operator-secret"},
    )

    assert response.status_code == 201
    assert "secure" in response.headers["set-cookie"].lower()


def test_operator_session_rejects_missing_and_invalid_environment_secret(
    tmp_path: Path,
) -> None:
    unconfigured = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "unconfigured.sqlite3"),
        now=lambda: NOW,
    )
    assert (
        _post(
            unconfigured,
            "/v1/workbench/operator-sessions",
            {"bootstrap_secret": "any-value"},
        ).status_code
        == 503
    )

    configured = create_app(
        runtime_state=lambda: _state(),
        database=_database(tmp_path / "configured.sqlite3"),
        now=lambda: NOW,
        bootstrap_secret="expected-secret",
    )
    response = _post(
        configured,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "wrong-secret"},
    )
    assert response.status_code == 401
    assert "wrong-secret" not in response.text


def test_cli_revokes_only_selected_browser_session(tmp_path: Path, monkeypatch) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    app = create_app(
        runtime_state=lambda: _state(),
        database=database,
        now=lambda: NOW,
        bootstrap_secret="test-operator-secret",
    )
    payload: dict[str, object] = {
        "tank_volume_gallons": 250,
        "pump_rated_flow_gph": 800,
        "delivered_flow_gph": 650,
        "minimum_turnover_per_hour": 2,
    }
    first_session = _post(
        app,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "test-operator-secret"},
    )
    assert first_session.status_code == 201
    first_session_id = database.list_active_operator_sessions(
        project_id="primary-reef-system",
        principal_id="local-acceptance-authority",
        authentication_generation=0,
    )[0].session_id
    second_session = _post(
        app,
        "/v1/workbench/operator-sessions",
        {"bootstrap_secret": "test-operator-secret"},
    )
    assert second_session.status_code == 201

    first_cookie = first_session.cookies.get("reefproof_session")
    second_cookie = second_session.cookies.get("reefproof_session")
    assert first_cookie is not None
    assert second_cookie is not None
    first_headers = {"Cookie": f"reefproof_session={first_cookie}"}
    second_headers = {"Cookie": f"reefproof_session={second_cookie}"}

    assert (
        _post(app, "/v1/workbench/policy-revisions", payload, headers=first_headers).status_code
        == 201
    )
    assert (
        _post(app, "/v1/workbench/policy-revisions", payload, headers=second_headers).status_code
        == 201
    )

    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))
    revoked = cli_runner.invoke(
        cli_app,
        ["auth", "revoke-session", "--session-id", first_session_id],
    )
    assert revoked.exit_code == 0, revoked.stdout

    assert (
        _post(app, "/v1/workbench/policy-revisions", payload, headers=first_headers).status_code
        == 401
    )
    assert (
        _post(app, "/v1/workbench/policy-revisions", payload, headers=second_headers).status_code
        == 201
    )


def test_stale_assurance_returns_readiness_503_but_liveness_remains_200(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    app = create_app(
        runtime_state=lambda: _state(last_valid_configuration_at=NOW - timedelta(seconds=601)),
        database=database,
        now=lambda: NOW,
    )
    assert _get(app, "/v1/system/health/live").status_code == 200
    ready = _get(app, "/v1/system/health/ready")
    assert ready.status_code == 503
    assert ready.json()["readiness"] == "unready"
    assert "stale" in ready.json()["reasons"][0].lower()


def test_findings_routes_return_typed_persisted_evidence(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    result = _critical_result()
    database.record_evaluation(
        EvaluationRun(
            evaluation_run_id=RUN_ID,
            evaluation_timestamp=NOW,
            policy_hash=HASH,
            results=(result,),
        )
    )
    database.record_alert_attempt(
        AlertAttempt(
            attempt_id="api-metrics-failure",
            invariant_id="RP-CIRC-001",
            adapter="home_assistant",
            action="send_new",
            attempted_at=NOW,
            result=AlertAttemptResult.FAILURE,
            duration_seconds=0.25,
            error_category="alert_delivery",
        )
    )
    app = create_app(
        runtime_state=lambda: _state(),
        database=database,
        now=lambda: NOW,
    )
    listing = _get(app, "/v1/findings")
    detail = _get(app, "/v1/findings/RP-CIRC-001")
    missing = _get(app, "/v1/findings/RP-NOPE-999")

    assert listing.status_code == 200
    assert listing.json()[0]["invariant_id"] == "RP-CIRC-001"
    assert detail.status_code == 200
    assert detail.json()["result"]["recommended_operator_action"]
    assert missing.status_code == 404

    metrics = _get(app, "/v1/system/metrics").text
    assert "reefproof_last_config_fetch_timestamp_seconds" in metrics
    assert "reefproof_last_config_change_timestamp_seconds" in metrics
    assert "reefproof_last_evaluation_timestamp_seconds" in metrics
    assert "reefproof_evaluation_duration_seconds 0.125" in metrics
    assert (
        'reefproof_invariant_results_total{invariant_id="RP-CIRC-001",'
        'severity="critical",state="FAIL"} 1.0'
    ) in metrics
    assert 'reefproof_build_info{commit="unknown",version=' in metrics
    assert (
        'reefproof_alert_attempts_total{adapter="home_assistant",result="failure"} 1.0' in metrics
    )
    assert (
        'reefproof_alert_delivery_duration_seconds{adapter="home_assistant",result="failure"} 0.25'
    ) in metrics
    assert 'reefproof_errors_total{category="alert_delivery",component="alerting"} 1.0' in metrics
    assert HASH not in metrics


def test_framework_mutation_errors_are_correlated_and_audited_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    app = create_app(runtime_state=lambda: _state(), database=database, now=lambda: NOW)

    @app.post("/v1/test-failure", include_in_schema=False)
    def fail_for_test() -> None:
        raise RuntimeError("sentinel private failure detail")

    client = _client(app)
    responses = (
        client.request("POST", "/v1/no-such-route"),
        client.request("POST", "/v1/system/status"),
        client.request("POST", "/v1/workbench/operator-sessions", json={"unexpected": True}),
        client.request("POST", "/v1/test-failure"),
    )
    assert [response.status_code for response in responses] == [404, 405, 422, 500]
    request_ids = [response.headers["X-ReefProof-Request-ID"] for response in responses]
    assert len(set(request_ids)) == 4

    with sqlite3.connect(database.path) as connection:
        rows = connection.execute(
            "SELECT request_id, route_name, outcome, status_code FROM api_mutation_audit "
            "WHERE request_id IN (?, ?, ?, ?) ORDER BY status_code",
            request_ids,
        ).fetchall()
    assert len(rows) == 4
    assert [row[3] for row in rows] == [404, 405, 422, 500]
    assert [row[2] for row in rows] == ["rejected", "rejected", "rejected", "failed"]
    assert "sentinel private failure detail" not in database.path.read_bytes().decode(
        "utf-8", errors="ignore"
    )
    assert "sentinel private failure detail" not in caplog.text


def test_only_post_policy_preview_is_exempt_from_mutation_audit(tmp_path: Path) -> None:
    database = _database(tmp_path / "reefproof.sqlite3")
    app = create_app(runtime_state=lambda: _state(), database=database, now=lambda: NOW)
    client = _client(app)

    preview = client.request("POST", "/v1/workbench/policy-preview", json={})
    attempts = [
        client.request(method, "/v1/workbench/policy-preview")
        for method in ("PUT", "PATCH", "DELETE")
    ]

    assert preview.status_code == 422
    assert [response.status_code for response in attempts] == [405, 405, 405]
    assert database.api_mutation_audit_count("/v1/workbench/policy-preview") == 3
