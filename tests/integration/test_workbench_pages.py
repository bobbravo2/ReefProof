from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI

from reefproof.api import create_app
from reefproof.service import RuntimeState
from reefproof.storage import Database

NOW = datetime(2026, 7, 25, 22, 30, tzinfo=UTC)


def _unreachable_runtime_state() -> RuntimeState:
    raise AssertionError("HTML routes must not inspect runtime state")


def _database(path: Path) -> Database:
    database = Database(path)
    database.migrate()
    return database


def _get(app: FastAPI, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _app(tmp_path: Path) -> FastAPI:
    return create_app(
        runtime_state=_unreachable_runtime_state,
        database=_database(tmp_path / "reefproof.sqlite3"),
        now=lambda: NOW,
    )


def test_workbench_areas_are_distinct_full_page_routes(tmp_path: Path) -> None:
    app = _app(tmp_path)
    routes = {
        "/workbench": ("overview", "Author, verify, and export"),
        "/workbench/system-map": ("system-map", "Trace canonical and observed identities"),
        "/workbench/assurance": ("assurance", "Author the return-flow policy"),
        "/workbench/evidence": ("evidence", "Know what ReefProof can prove"),
        "/workbench/sessions": ("sessions", "Review durable authorship history"),
        "/workbench/database": ("database", "Inspect the durable SQLite boundary"),
    }

    for route, (page, heading) in routes.items():
        response = _get(app, route)
        assert response.status_code == 200
        assert f'data-workbench-page="{page}"' in response.text
        assert heading in response.text
        assert f'href="{route}" aria-current="page"' in response.text
        assert 'href="/workbench"' in response.text
        assert 'href="/workbench/system-map"' in response.text
        assert 'href="/workbench/assurance"' in response.text
        assert 'href="/workbench/evidence"' in response.text
        assert 'href="/workbench/sessions"' in response.text
        assert 'href="/workbench/database"' in response.text
        assert 'href="#page-content"' in response.text
        assert '<script type="module" src="/assets/workbench.js?v=' in response.text
        assert '<link rel="stylesheet" href="/assets/workbench-pages.css?v=' in response.text


def test_each_workbench_route_contains_only_its_primary_workflow(tmp_path: Path) -> None:
    app = _app(tmp_path)

    overview = _get(app, "/workbench").text
    assert "Primary project" in overview
    assert "Author, verify, and export" in overview
    assert 'id="project-session-form"' in overview
    assert 'id="project-overview"' in overview
    assert 'id="electrical-posture"' in overview
    assert 'data-electrical="headline"' in overview
    assert "Counts and categories only; redacted values never reach this view." in overview
    assert 'data-project="recommendation"' in overview
    assert "DETERMINISTIC · NO LLM" in overview
    assert 'id="flow-form"' not in overview
    assert 'id="rule-catalog"' not in overview
    assert 'id="physical-twin"' not in overview

    assurance = _get(app, "/workbench/assurance").text
    assert 'id="flow-form"' in assurance
    assert 'id="preview"' in assurance
    assert 'id="rule-catalog"' not in assurance
    assert 'id="physical-twin"' not in assurance

    evidence = _get(app, "/workbench/evidence").text
    assert 'id="evidence-heading"' in evidence
    assert 'id="evidence-revision"' in evidence
    assert 'id="rule-catalog"' in evidence
    assert "It can prove" in evidence
    assert "It does not prove" in evidence
    assert "UNKNOWN remains distinct from PASS" in evidence
    assert 'id="trust-session-form"' in evidence
    assert 'id="trust-revocation-form"' in evidence
    assert 'id="trust-restoration-form"' in evidence
    assert 'id="totp-confirm-form"' in evidence
    assert "Revoke reliance without rewriting history" in evidence
    assert 'id="flow-form"' not in evidence
    assert 'id="physical-twin"' not in evidence

    system_map = _get(app, "/workbench/system-map").text
    assert 'id="reconciliation-status"' in system_map
    assert "never guesses by name or topology" in system_map
    assert 'id="physical-twin"' not in system_map
    assert 'id="flow-form"' not in system_map
    assert 'id="rule-catalog"' not in system_map

    sessions = _get(app, "/workbench/sessions").text
    assert 'id="project-session-form"' in sessions
    assert 'id="project-sessions"' in sessions
    assert 'id="interview-session-list"' in sessions
    assert 'id="candidate-review-list"' in sessions
    assert "Credentials stay out of evidence" in sessions
    assert "It cannot mutate HYDROS" in sessions
    assert 'id="flow-form"' not in sessions
    assert 'id="rule-catalog"' not in sessions
    assert 'id="physical-twin"' not in sessions

    database = _get(app, "/workbench/database").text
    assert 'id="database-session-form"' in database
    assert 'id="database-explorer"' in database
    assert 'id="database-table-list"' in database
    assert 'id="database-column-table"' in database
    assert 'id="database-row-table"' in database
    assert "QUERY ONLY" in database
    assert "NO SQL INPUT" in database
    assert "not canonical project truth" in database
    assert 'id="flow-form"' not in database
    assert 'id="project-session-form"' not in database


def test_workbench_page_styles_are_external_and_unknown_routes_fail(tmp_path: Path) -> None:
    app = _app(tmp_path)

    stylesheet = _get(app, "/assets/workbench-pages.css")
    assert stylesheet.status_code == 200
    assert '.site-nav__links a[aria-current="page"]' in stylesheet.text
    assert ".evidence-layout" in stylesheet.text
    assert "@media (max-width: 42rem)" in stylesheet.text
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet.text

    assert _get(app, "/workbench/not-a-page").status_code == 404


def test_operator_session_gate_explains_alternative_credentials_and_reflows(
    tmp_path: Path,
) -> None:
    app = _app(tmp_path)
    workbench = _get(app, "/workbench").text
    stylesheet = _get(app, "/assets/workbench-pages.css").text

    assert "Unlock Workbench" in workbench
    assert "Operator access" in workbench
    assert "session ends when ReefProof stops" in workbench
    assert "First-time access" in workbench
    assert "Returning operator" in workbench
    assert "Credentials are used only to establish this session" in workbench
    assert "LOCAL · NOT LIVE" in workbench
    assert 'id="auth-method-bootstrap"' in workbench
    assert 'id="auth-method-totp"' in workbench
    assert 'name="bootstrap_secret"' in workbench
    assert 'name="totp_code" inputmode="numeric"' in workbench
    assert 'autocomplete="one-time-code"' in workbench
    assert 'role="status" hidden' in workbench
    assert ".session-auth-options," in stylesheet
    assert ".session-auth-form__action" in stylesheet


def test_workbench_promises_only_available_manual_workflows(tmp_path: Path) -> None:
    app = _app(tmp_path)
    overview = _get(app, "/workbench").text
    assurance = _get(app, "/workbench/assurance").text

    assert "Fetch and review the six-tab authored-system source" in overview
    assert "Record bounded physical verification" in overview
    assert "Preview and export deterministic" in overview
    assert "Review unproven mappings" not in overview
    assert "Complete electrical mappings" not in overview
    assert "Understand the system" not in overview
    assert "exact evidence behind every result" not in overview
    assert "Move the assurance model forward" not in overview
    assert "aquarium-scene" not in overview
    assert overview.count('name="bootstrap_secret"') == 1
    assert overview.count('name="totp_code"') == 2
    assert assurance.count('name="bootstrap_secret"') == 1
    assert assurance.count('name="totp_code"') == 1
