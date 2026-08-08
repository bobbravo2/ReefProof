from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from reefproof.configuration import (
    ConfigurationFixture,
    EntityType,
    load_fixture,
    render_snapshot,
    snapshot_fixture,
    stable_entity_id,
    write_snapshot,
)

FIXTURE = Path("tests/fixtures/configuration/authored-minimal.json")
GOLDEN = Path("tests/golden/configuration/authored-minimal.snapshot.json")


def test_loads_authored_fixture_and_preserves_source_payload() -> None:
    fixture = load_fixture(FIXTURE)

    assert fixture.provenance == "AUTHORED"
    assert fixture.payload["vendor_extensions"] == {
        "synthetic_notice": "Authored test data; not an observed HYDROS export."
    }


def test_normalizes_observed_entities_and_separate_annotations() -> None:
    snapshot = snapshot_fixture(load_fixture(FIXTURE))

    assert len(snapshot.entities) == 2
    assert len(snapshot.authored_entities) == 1
    assert len(snapshot.annotations) == 1
    annotation = snapshot.annotations[0]
    return_device = next(
        entity for entity in snapshot.entities if entity.display_name == "Example Return"
    )
    assert annotation.subject_id == return_device.reefproof_id
    power_domain = snapshot.authored_entities[0]
    assert annotation.target_id == power_domain.reefproof_id
    assert annotation.value is None
    assert annotation.owner == "example-operator"
    assert snapshot.configuration_hash.startswith("sha256:")
    assert snapshot.annotation_hash.startswith("sha256:")
    assert snapshot.snapshot_hash.startswith("sha256:")


def test_stable_entity_id_prefers_vendor_identity() -> None:
    first = stable_entity_id(
        entity_type=EntityType.CONTROLLER,
        vendor_id="controller-1",
        source_path="$.first",
    )
    moved = stable_entity_id(
        entity_type=EntityType.CONTROLLER,
        vendor_id="controller-1",
        source_path="$.moved",
    )

    assert first == moved
    assert first.startswith("RP.CONTROLLER.")


def test_snapshot_rendering_is_deterministic() -> None:
    fixture = load_fixture(FIXTURE)
    first = render_snapshot(snapshot_fixture(fixture))
    reordered_document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reordered_document["payload"]["entities"].reverse()
    reordered = ConfigurationFixture.model_validate(reordered_document)
    second = render_snapshot(snapshot_fixture(reordered))

    assert first == second


def test_snapshot_matches_golden_evidence() -> None:
    rendered = render_snapshot(snapshot_fixture(load_fixture(FIXTURE)))

    assert rendered == GOLDEN.read_text(encoding="utf-8")


def test_snapshot_changes_when_observed_configuration_changes() -> None:
    fixture = load_fixture(FIXTURE)
    changed_document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    changed_document["payload"]["entities"][0]["display_name"] = "Changed Controller"
    changed = ConfigurationFixture.model_validate(changed_document)

    assert snapshot_fixture(fixture).snapshot_hash != snapshot_fixture(changed).snapshot_hash


def test_writes_snapshot_atomically(tmp_path: Path) -> None:
    snapshot = snapshot_fixture(load_fixture(FIXTURE))
    output = tmp_path / "nested" / "snapshot.json"

    write_snapshot(snapshot, output)

    assert output.read_text(encoding="utf-8") == render_snapshot(snapshot)
    assert not list(output.parent.glob("*.tmp"))


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"fixture_version":"0.1","fixture_version":"0.1",'
        '"provenance":"AUTHORED","source_format":"synthetic","payload":{}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON object key: fixture_version"):
        load_fixture(path)


def test_rejects_unknown_envelope_fields(tmp_path: Path) -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["device_id"] = "private-device"
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_fixture(path)


def test_rejects_unknown_annotation_subject() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["payload"]["annotations"][0]["subject_key"] = "missing"
    fixture = ConfigurationFixture.model_validate(document)

    with pytest.raises(ValidationError, match="unknown annotation subject_key: missing"):
        snapshot_fixture(fixture)


def test_preserves_extensions_and_reports_unknown_confidence() -> None:
    snapshot = snapshot_fixture(load_fixture(FIXTURE))

    controller = next(
        entity for entity in snapshot.entities if entity.display_name == "Example Controller"
    )
    assert controller.vendor_extensions == {"authored_example": True}
    assert snapshot.vendor_extensions["synthetic_notice"] == (
        "Authored test data; not an observed HYDROS export."
    )
    assert snapshot.completeness_warnings == (
        "Unmodeled fixture-level vendor extensions are preserved.",
        "One or more observed entities have unknown confidence.",
    )
