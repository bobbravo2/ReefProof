from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.service import import_hydros_export
from reefproof.storage import Database

FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-sanitized.json")
SECRET_FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-secret-bearing.json")
CAPTURED_AT = datetime.fromisoformat("2026-07-31T19:45:00-04:00")
EVALUATED_AT = datetime.fromisoformat("2026-07-31T20:15:00-04:00")


def test_operator_confirmed_fahrenheit_pass_is_persisted(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()

    completed = import_hydros_export(
        FIXTURE,
        captured_at=CAPTURED_AT,
        expected_temperature_unit="fahrenheit",
        database=database,
        evaluation_timestamp=EVALUATED_AT,
        evaluation_run_id="82345678-abcd-4234-8234-123456789abc",
    )

    result = completed.evaluation.results[0]
    assert completed.snapshot_inserted is True
    assert result.state == "PASS"
    assert result.invariant_id == "RP-UNIT-001"
    assert result.evidence == ('$.Option["Option"].tempFmt = "1"',)
    assert database.snapshot_count() == 1
    summary = database.evaluation_summary(completed.evaluation.evaluation_run_id)
    assert summary.pass_count == 1
    assert summary.fail_count == 0
    assert summary.unknown_count == 0
    assert database.active_finding("RP-UNIT-001") is None


def test_secret_values_are_absent_from_persisted_normalized_snapshot(tmp_path: Path) -> None:
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()

    import_hydros_export(
        SECRET_FIXTURE,
        captured_at=CAPTURED_AT,
        expected_temperature_unit="fahrenheit",
        database=database,
        evaluation_timestamp=EVALUATED_AT,
        evaluation_run_id="92345678-abcd-4234-8234-123456789abc",
    )

    snapshot = database.latest_snapshot()
    assert snapshot is not None
    serialized = snapshot.model_dump_json()
    assert "SEED-TUYA-LOCAL-KEY-6294" not in serialized
    assert "SEED-WIFI-PASSWORD-2390" not in serialized
    manifest = snapshot.vendor_extensions["redaction_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["redacted_field_count"] == 13
