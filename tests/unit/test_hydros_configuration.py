from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from reefproof.configuration import load_hydros_export, snapshot_hydros_export

FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-sanitized.json")
SECRET_FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-secret-bearing.json")
CAPTURED_AT = datetime.fromisoformat("2026-07-31T19:45:00-04:00")

SEEDED_PRIVATE_VALUES = (
    "SEED-SERIAL-8842",
    "SEED-ACCOUNT-THING-5519",
    "SEED-UNIT-4471",
    "SEED-WIFI-PASSWORD-2390",
    "SEED-SSID-7781",
    "192.0.2.44",
    "SEED-ACCOUNT-9913",
    "SEED-TUYA-LOCAL-KEY-6294",
    "SEED-TUYA-DEVICE-3370",
    "198.51.100.17",
    "SEED-TUYA-TOKEN-1058",
)


def test_normalizes_observed_hydros_objects_without_inferred_relationships() -> None:
    snapshot = snapshot_hydros_export(FIXTURE, captured_at=CAPTURED_AT)

    assert snapshot.provenance == "OBSERVED"
    assert snapshot.source_format == "hydros_chrome_download_config"
    assert snapshot.captured_at == CAPTURED_AT
    assert len(snapshot.entities) == 5
    assert snapshot.authored_entities == ()
    assert snapshot.annotations == ()
    assert all(entity.confidence == "unknown" for entity in snapshot.entities)
    assert all(
        entity.raw_configuration_hash == snapshot.configuration_hash for entity in snapshot.entities
    )
    manifest = snapshot.vendor_extensions["redaction_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["redacted_field_count"] == 9
    system = next(entity for entity in snapshot.entities if entity.entity_type == "controller")
    assert system.observed_properties == {
        "temperature_display_unit": {
            "value": "fahrenheit",
            "source_path": '$.Option["Option"].tempFmt',
            "confidence": "operator_confirmed",
        }
    }


def test_raw_byte_hash_changes_even_when_tolerant_json_value_is_equivalent(tmp_path: Path) -> None:
    strict_path = tmp_path / "strict.json"
    tolerant_path = tmp_path / "tolerant.json"
    strict_path.write_text('{"System":{"System":{"friendlyName":"A B"}}}', encoding="utf-8")
    tolerant_path.write_bytes(b'{"System":{"System":{"friendlyName":"A\x19B"}}}')

    strict = snapshot_hydros_export(strict_path, captured_at=CAPTURED_AT)
    tolerant = snapshot_hydros_export(tolerant_path, captured_at=CAPTURED_AT)

    assert strict.configuration_hash != tolerant.configuration_hash
    assert any("tolerant JSON parsing" in warning for warning in tolerant.completeness_warnings)


def test_rejects_duplicate_keys_and_unknown_sections(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"System":{},"System":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_hydros_export(duplicate)

    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"Credentials": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unrecognized HYDROS export sections"):
        load_hydros_export(unknown)


def test_secret_bearing_values_cannot_escape_normalized_snapshot() -> None:
    snapshot = snapshot_hydros_export(SECRET_FIXTURE, captured_at=CAPTURED_AT)
    serialized = snapshot.model_dump_json()

    for private_value in SEEDED_PRIVATE_VALUES:
        assert private_value not in serialized

    assert all(entity.vendor_id is None for entity in snapshot.entities)
    controller = next(
        entity for entity in snapshot.entities if entity.display_name == "Synthetic Controller"
    )
    assert controller.vendor_extensions == {
        "device": 1,
        "friendlyName": "Synthetic Controller",
        "thingType": "Controller",
        "type": "Device",
    }
    manifest = snapshot.vendor_extensions["redaction_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["redacted_field_count"] == 13
    redacted_paths = manifest["redacted_paths"]
    assert isinstance(redacted_paths, list)
    string_paths = [path for path in redacted_paths if isinstance(path, str)]
    assert len(string_paths) == len(redacted_paths)
    assert string_paths == sorted(string_paths)
    assert '$.TpDevice["Synthetic Tuya Strip"].localKey' in string_paths
    assert manifest["categories"] == {
        "account_identifier": 2,
        "credential": 3,
        "device_identifier": 5,
        "network_identifier": 3,
    }
