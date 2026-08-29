from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from typer.testing import CliRunner

from reefproof.authored_sources import (
    AuthoredSourceConfiguration,
    AuthoredSourceSnapshot,
    AuthoredSourceStore,
    AuthoredSourceTab,
    GoogleSheetsSource,
    ImportChangeState,
    SourceTabName,
    authored_source_status,
    build_import_review,
    import_candidates,
    normalize_source_snapshot,
)
from reefproof.authored_sources.models import SOURCE_TAB_NAMES, source_snapshot_hash
from reefproof.candidate_validation import validate_candidate
from reefproof.cli import app
from reefproof.cli_domains import source as source_commands
from reefproof.project_store import ProjectStore

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
runner = CliRunner()


def _rows(
    **overrides: tuple[tuple[str, ...], ...],
) -> dict[SourceTabName, tuple[tuple[str, ...], ...]]:
    values = {
        SourceTabName.BOM: (("BOM_ID", "ITEM_NAME", "POWER_DOMAIN_ID"), ("BOM-1", "Pump", "PD-1")),
        SourceTabName.DOMAINS: (("DOMAIN_ID", "NAME"), ("PD-1", "Main circuit")),
        SourceTabName.POWER: (
            ("POWER_ID", "DOMAIN_ID", "POWER_SUPPLY_ID", "LOCATION"),
            ("PWR-1", "PD-1", "PSU-1", "Cabinet"),
        ),
        SourceTabName.DEVICE_INTERFACES: (
            (
                "INTERFACE_ID",
                "DEVICE_ID",
                "BOM_ID",
                "POWER_DOMAIN_ID",
                "PORT_ID",
                "LOCATION",
                "CABLE_ID",
                "FROM_ZONE",
                "FROM_DEVICE",
                "FROM_PORT",
                "TO_ZONE",
                "TO_DEVICE",
                "TO_PORT",
            ),
            (
                "IF-1",
                "DEV-1",
                "BOM-1",
                "PD-1",
                "PORT-1",
                "Sump",
                "CBL-0001",
                "Cabinet",
                "Controller",
                "Output 1",
                "Sump",
                "Return Pump",
                "Power",
            ),
        ),
        SourceTabName.OUTPUTS: (
            ("OUTPUT_ID", "DEVICE_ID", "MODE_ID"),
            ("OUT-1", "DEV-1", "MODE-1"),
        ),
        SourceTabName.MODES: (("MODE_ID", "NAME"), ("MODE-1", "Normal")),
    }
    values.update({SourceTabName(name): rows for name, rows in overrides.items()})
    return values


def _snapshot(**overrides: tuple[tuple[str, ...], ...]) -> AuthoredSourceSnapshot:
    rows = _rows(**overrides)
    tabs = tuple(
        AuthoredSourceTab(name=name, source_range=f"'{name.value}'!A1:ZZ10000", rows=rows[name])
        for name in SOURCE_TAB_NAMES
    )
    return AuthoredSourceSnapshot(
        source_snapshot_id="fixture-snapshot",
        source_alias="primary-design",
        spreadsheet_id="sheet-fixture",
        spreadsheet_title="Primary Reef System",
        fetched_at=NOW,
        tabs=tabs,
        snapshot_hash=source_snapshot_hash(tabs),
    )


def test_six_tab_normalization_is_deterministic_and_retains_provenance() -> None:
    first = normalize_source_snapshot(_snapshot())
    second = normalize_source_snapshot(_snapshot())

    assert first == second
    assert first.valid
    assert first.record_counts == {
        SourceTabName.BOM: 1,
        SourceTabName.DOMAINS: 1,
        SourceTabName.POWER: 1,
        SourceTabName.DEVICE_INTERFACES: 1,
        SourceTabName.OUTPUTS: 1,
        SourceTabName.MODES: 1,
    }
    interface = next(
        record for record in first.records if record.tab is SourceTabName.DEVICE_INTERFACES
    )
    assert interface.external_namespace == "INTERFACE_ID"
    assert interface.external_id == "IF-1"
    assert interface.provenance.source_range == "DEVICE_INTERFACES!2:2"


def test_distinct_external_ids_cannot_collide_in_canonical_namespace() -> None:
    batch = normalize_source_snapshot(
        _snapshot(
            BOM=(
                ("BOM_ID", "ITEM_NAME", "POWER_DOMAIN_ID"),
                ("BOM 1", "First pump", "PD-1"),
                ("BOM-1", "Second pump", "PD-1"),
            )
        )
    )
    assert batch.valid
    try:
        import_candidates(
            batch,
            project_id="primary-reef-system",
            proposed_by_actor_id="source-parser",
            proposed_at=NOW,
        )
    except ValueError as error:
        assert "collide" in str(error)
    else:
        raise AssertionError("canonical slug collision must fail closed")


def test_duplicate_ambiguous_headers_fail_closed() -> None:
    batch = normalize_source_snapshot(
        _snapshot(
            DEVICE_INTERFACES=(
                ("INTERFACE_ID", "DEVICE_ID", "POWER_DOMAIN_ID", "POWER_DOMAIN_ID"),
                ("IF-1", "DEV-1", "PD-1", "PD-2"),
            )
        )
    )

    assert not batch.valid
    assert [(item.code, item.tab) for item in batch.diagnostics] == [
        ("DUPLICATE_HEADER", SourceTabName.DEVICE_INTERFACES)
    ]


def test_duplicate_ids_formula_errors_and_broken_references_fail_closed() -> None:
    batch = normalize_source_snapshot(
        _snapshot(
            BOM=(
                ("BOM_ID", "ITEM_NAME", "POWER_DOMAIN_ID"),
                ("BOM-1", "Pump", "MISSING"),
                ("BOM-1", "#REF!", "PD-1"),
            ),
        )
    )

    assert not batch.valid
    assert {item.code for item in batch.diagnostics} == {
        "DUPLICATE_EXTERNAL_ID",
        "UNRESOLVED_FOREIGN_KEY",
    }


class _Credentials:
    def authorization_headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer synthetic-read-only-token"}


def test_google_sheets_source_uses_only_bounded_read_only_gets() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/values:batchGet"):
            value_ranges = [
                {
                    "range": f"'{name.value}'!A1:ZZ10000",
                    "values": [list(row) for row in _rows()[name]],
                }
                for name in SOURCE_TAB_NAMES
            ]
            return httpx.Response(200, json={"valueRanges": value_ranges})
        return httpx.Response(
            200,
            json={
                "spreadsheetId": "sheet-fixture",
                "properties": {"title": "Primary Reef System"},
                "sheets": [{"properties": {"title": name.value}} for name in SOURCE_TAB_NAMES],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    snapshot = GoogleSheetsSource(
        spreadsheet_id="sheet-fixture",
        source_alias="primary-design",
        credentials=_Credentials(),
        client=client,
        now=lambda: NOW,
    ).fetch()

    assert tuple(tab.name for tab in snapshot.tabs) == SOURCE_TAB_NAMES
    assert len(requests) == 2
    assert {request.method for request in requests} == {"GET"}
    assert all(request.url.host == "sheets.googleapis.com" for request in requests)
    assert all(
        request.headers["authorization"] == "Bearer synthetic-read-only-token"
        for request in requests
    )
    query = requests[1].url.query.decode()
    assert query.count("ranges=") == 6
    assert "A1%3AZZ10000" in query


def test_google_sheets_source_rejects_missing_required_tab_before_values_fetch() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "properties": {"title": "Incomplete"},
                    "sheets": [
                        {"properties": {"title": name.value}}
                        for name in SOURCE_TAB_NAMES
                        if name is not SourceTabName.MODES
                    ],
                }
            ).encode(),
        )

    source = GoogleSheetsSource(
        spreadsheet_id="sheet-fixture",
        source_alias="primary-design",
        credentials=_Credentials(),
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        now=lambda: NOW,
    )
    try:
        source.fetch()
    except ValueError as error:
        assert str(error) == "Google Sheet is missing required tab(s): MODES"
    else:
        raise AssertionError("missing tab must fail closed")


def test_source_validate_reports_bounded_evidence_without_persisting(tmp_path, monkeypatch) -> None:
    class _Source:
        def fetch(self) -> AuthoredSourceSnapshot:
            return _snapshot()

    monkeypatch.setattr(source_commands, "_configured_source", lambda: _Source())
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))

    result = runner.invoke(app, ["source", "validate"])

    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["status"] == "VALID"
    assert document["tabs"] == [name.value for name in SOURCE_TAB_NAMES]
    assert document["record_counts"]["BOM"] == 1
    assert "BOM-1" not in result.stdout
    assert not (tmp_path / "reefproof.sqlite3").exists()


def test_source_freshness_and_fetch_failure_do_not_change_retained_evidence() -> None:
    configuration = AuthoredSourceConfiguration(
        source_configuration_id="config-1",
        project_id="primary-reef-system",
        source_alias="primary-design",
        spreadsheet_id="sheet-fixture",
        configured_at=NOW,
        freshness_seconds=60,
    )
    snapshot = _snapshot()

    assert (
        authored_source_status(
            configuration=configuration, latest_snapshot=snapshot, now=NOW
        ).health
        == "CURRENT"
    )
    assert (
        authored_source_status(
            configuration=configuration,
            latest_snapshot=snapshot,
            now=NOW + timedelta(seconds=61),
        ).health
        == "STALE"
    )
    unavailable = authored_source_status(
        configuration=configuration,
        latest_snapshot=snapshot,
        now=NOW + timedelta(seconds=61),
        fetch_error="transport",
    )
    assert unavailable.health == "UNAVAILABLE"
    assert unavailable.latest_snapshot_hash == snapshot.snapshot_hash


def test_valid_import_creates_deterministic_noncanonical_candidates() -> None:
    batch = normalize_source_snapshot(_snapshot())
    candidates = import_candidates(
        batch,
        project_id="primary-reef-system",
        proposed_by_actor_id="source-parser",
        proposed_at=NOW,
    )

    assert candidates
    assert candidates == import_candidates(
        batch,
        project_id="primary-reef-system",
        proposed_by_actor_id="source-parser",
        proposed_at=NOW,
    )
    assert all(
        candidate.subject_id.startswith("rp:primary-reef-system:") for candidate in candidates
    )
    assert all(validate_candidate(candidate, validated_at=NOW).is_valid for candidate in candidates)
    unsupported = candidates[0].model_copy(update={"attribute": "device.unexpected"})
    validation = validate_candidate(unsupported, validated_at=NOW)
    assert not validation.is_valid
    assert validation.reason_codes == ("import_candidate_invalid",)


def test_source_load_persists_review_batch_without_canonical_acceptance(
    tmp_path, monkeypatch
) -> None:
    class _Source:
        def fetch(self) -> AuthoredSourceSnapshot:
            return _snapshot()

    monkeypatch.setattr(source_commands, "_configured_source", lambda: _Source())
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))

    first = runner.invoke(app, ["source", "load"])
    second = runner.invoke(app, ["source", "load"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    first_document = json.loads(first.stdout)
    assert first_document["status"] == "PENDING_REVIEW"
    assert first_document["inserted"] is True
    assert first_document["candidate_count"] > 6
    assert first_document["canonical_fact_count"] == 0
    assert json.loads(second.stdout)["inserted"] is False


def test_invalid_source_load_persists_diagnostics_without_candidates(tmp_path, monkeypatch) -> None:
    invalid_snapshot = _snapshot(
        DEVICE_INTERFACES=(
            ("INTERFACE_ID", "DEVICE_ID", "POWER_DOMAIN_ID", "POWER_DOMAIN_ID"),
            ("IF-1", "DEV-1", "PD-1", "PD-2"),
        )
    )

    class _Source:
        def fetch(self) -> AuthoredSourceSnapshot:
            return invalid_snapshot

    monkeypatch.setattr(source_commands, "_configured_source", lambda: _Source())
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path))

    result = runner.invoke(app, ["source", "load"])

    assert result.exit_code == 2, result.stdout
    document = json.loads(result.stdout)
    assert document["status"] == "INVALID"
    assert document["candidate_count"] == 0
    assert document["canonical_fact_count"] == 0
    assert document["diagnostics"][0]["code"] == "DUPLICATE_HEADER"
    source_store = AuthoredSourceStore(tmp_path / "reefproof.sqlite3")
    latest_import = source_store.latest_import("primary-reef-system")
    assert latest_import is not None
    assert latest_import.valid is False
    assert ProjectStore(tmp_path / "reefproof.sqlite3").list_sessions("primary-reef-system") == ()


def test_first_batch_load_verify_accept_and_csv_export(tmp_path, monkeypatch) -> None:
    class _Source:
        def fetch(self) -> AuthoredSourceSnapshot:
            return _snapshot()

    class _Totp:
        def __init__(self, _path, *, principal_id: str) -> None:
            assert principal_id == "local-acceptance-authority"

        def verify(self, code: str) -> datetime:
            assert code == "123456"
            return NOW

    monkeypatch.setattr(source_commands, "_configured_source", lambda: _Source())
    monkeypatch.setattr("reefproof.cli.TotpState", _Totp)
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "data"))

    validation = runner.invoke(app, ["source", "validate"])
    loaded = runner.invoke(app, ["source", "load"])
    session_id = json.loads(loaded.stdout)["session_id"]
    reviewed = runner.invoke(app, ["source", "review", session_id])
    accepted = runner.invoke(
        app,
        [
            "source",
            "accept",
            session_id,
            "--totp-code",
            "123456",
            "--rationale",
            "Verified first authored batch against the source review.",
        ],
    )
    output = tmp_path / "first-label-batch.csv"
    exported = runner.invoke(app, ["labels", "export", "--output", str(output)])

    assert validation.exit_code == 0, validation.stdout
    assert loaded.exit_code == 0, loaded.stdout
    assert reviewed.exit_code == 0, reviewed.stdout
    assert accepted.exit_code == 0, accepted.stdout
    assert exported.exit_code == 0, exported.stdout
    assert json.loads(accepted.stdout)["accepted_candidate_count"] > 0
    review_document = json.loads(reviewed.stdout)
    assert review_document["status"] == "READY_FOR_DECISION"
    assert review_document["state_counts"]["NEW"] > 0
    assert all(item["source_range"] for item in review_document["objects"])
    assert json.loads(exported.stdout)["label_count"] == 4
    csv_document = output.read_text(encoding="utf-8")
    assert "DEVICE,DEV-1" in csv_document
    assert "PORT,PORT-1" in csv_document
    assert "CABLE,CBL-0001" in csv_document
    assert "POWER SUPPLY,PSU-1" in csv_document
    database_path = tmp_path / "data" / "reefproof.sqlite3"
    source_store = AuthoredSourceStore(database_path)
    bindings = source_store.list_bindings("primary-reef-system")
    batch = source_store.latest_import("primary-reef-system")
    assert batch is not None
    assert {binding.namespace for binding in bindings}.issuperset(
        {"DEVICE_ID", "PORT_ID", "CABLE_ID", "POWER_SUPPLY_ID"}
    )
    review = build_import_review(
        batch,
        project_id="primary-reef-system",
        state=ProjectStore(database_path).replay("primary-reef-system"),
        bindings=bindings,
        source_instance="sheet-fixture",
    )
    assert {item.state for item in review.objects} == {"UNCHANGED"}
    changed = normalize_source_snapshot(
        _snapshot(
            BOM=(
                ("BOM_ID", "ITEM_NAME", "POWER_DOMAIN_ID"),
                ("BOM-1", "Changed pump", "PD-1"),
            )
        )
    )
    changed_review = build_import_review(
        changed,
        project_id="primary-reef-system",
        state=ProjectStore(database_path).replay("primary-reef-system"),
        bindings=bindings,
        source_instance="sheet-fixture",
    )
    assert changed_review.state_counts[ImportChangeState.CHANGED] == 1
    removed_mode = batch.model_copy(
        update={
            "records": tuple(
                record for record in batch.records if record.tab is not SourceTabName.MODES
            )
        }
    )
    removed_review = build_import_review(
        removed_mode,
        project_id="primary-reef-system",
        state=ProjectStore(database_path).replay("primary-reef-system"),
        bindings=bindings,
        source_instance="sheet-fixture",
    )
    assert removed_review.state_counts[ImportChangeState.REMOVED_FROM_SOURCE] == 1
