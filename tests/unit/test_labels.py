from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from reefproof.authored_sources.review import ExternalIdentityBinding
from reefproof.cli import app
from reefproof.labels import (
    LabelKind,
    generate_label_manifest,
    label_export_filename,
    render_label_csv,
)
from reefproof.project_state import CanonicalFact, ProjectState

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
runner = CliRunner()


def _fact(subject: str, attribute: str, value: str) -> CanonicalFact:
    return CanonicalFact(
        subject_id=subject,
        attribute=attribute,
        value=value,
        source_candidate_fact_id=f"candidate-{attribute.replace('.', '-')}",
        accepted_by_actor_id="local-acceptance-authority",
        accepted_at=NOW,
        evidence_ids=("evidence-source-snapshot-1",),
    )


def _state(*, complete_cable: bool = True) -> ProjectState:
    interface = "rp:primary-reef-system:interface:if-1"
    power = "rp:primary-reef-system:power:pwr-1"
    values = [
        _fact(interface, "interface.device_id", "DEV-1"),
        _fact(interface, "interface.port_id", "PORT-1"),
        _fact(interface, "interface.location", "Sump"),
        _fact(interface, "interface.cable_id", "CBL-0001"),
        _fact(interface, "interface.from_zone", "Cabinet"),
        _fact(interface, "interface.from_device", "Controller"),
        _fact(interface, "interface.from_port", "Output 1"),
        _fact(interface, "interface.to_zone", "Sump"),
        _fact(interface, "interface.to_device", "Return Pump"),
        _fact(power, "power.power_supply_id", "PSU-1"),
        _fact(power, "power.location", "Cabinet"),
    ]
    if complete_cable:
        values.append(_fact(interface, "interface.to_port", "Power"))
    return ProjectState(
        project_id="primary-reef-system", facts=tuple(values), last_sequence=len(values)
    )


def test_manifest_and_csv_are_deterministic_for_all_label_kinds() -> None:
    first = generate_label_manifest(_state(), project_name="Primary Reef System")
    second = generate_label_manifest(_state(), project_name="Primary Reef System")

    assert first == second
    assert (
        label_export_filename("Primary Reef / System", version="0.1.2")
        == "reefproof-primary-reef-system-v0.1.2-labels.csv"
    )
    assert {record.label_kind for record in first.records} == set(LabelKind)
    cable = next(record for record in first.records if record.label_kind is LabelKind.CABLE)
    assert cable.copies == 2
    assert cable.primary_text == "FROM: Cabinet · Controller · Output 1"
    assert cable.secondary_text == "TO: Sump · Return Pump · Power | CABLE: CBL-0001"
    csv_document = render_label_csv(first)
    assert csv_document == render_label_csv(second)
    assert csv_document.startswith("label_kind,display_id,from_zone")
    assert "CABLE,CBL-0001,Cabinet,Controller,Output 1,Sump,Return Pump,Power" in csv_document
    assert "POWER SUPPLY,PSU-1" in csv_document


def test_cable_label_fails_closed_without_two_complete_endpoints() -> None:
    with pytest.raises(ValueError, match="complete FROM and TO endpoints"):
        generate_label_manifest(_state(complete_cable=False), project_name="Primary Reef System")


def test_non_sheet_identity_evidence_is_not_treated_as_source_import_provenance() -> None:
    device_id = "rp:primary-reef-system:device:dev-1"
    manifest = generate_label_manifest(
        _state(),
        project_name="Primary Reef System",
        bindings=(
            ExternalIdentityBinding(
                binding_id="binding-sheet",
                project_id="primary-reef-system",
                source_instance="sheet-fixture",
                namespace="DEVICE_ID",
                value="DEV-1",
                canonical_subject_id=device_id,
                import_batch_id="import-fixture",
                accepted_at=NOW,
            ),
            ExternalIdentityBinding(
                binding_id="binding-hydros",
                project_id="primary-reef-system",
                source_system="hydros",
                source_instance="sha256:observed",
                namespace="reefproof_id",
                value="RP.CONTROLLER.fixture",
                canonical_subject_id=device_id,
                evidence_reference="onsite comparison",
                rationale="Explicit operator match.",
                accepted_at=NOW,
            ),
        ),
    )

    device = next(record for record in manifest.records if record.label_kind is LabelKind.DEVICE)
    assert device.source_import_batch_ids == ("import-fixture",)


def test_cli_exports_first_csv_batch_without_overwriting(tmp_path, monkeypatch) -> None:
    class _Store:
        def __init__(self, _path) -> None:
            pass

        def replay(self, _project_id: str) -> ProjectState:
            return _state()

    class _SourceStore:
        def __init__(self, _path) -> None:
            pass

        def list_bindings(self, _project_id: str) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr("reefproof.project_store.ProjectStore", _Store)
    monkeypatch.setattr("reefproof.authored_sources.AuthoredSourceStore", _SourceStore)
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "data"))
    output = tmp_path / "first-label-batch.csv"

    result = runner.invoke(app, ["labels", "export", "--output", str(output)])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["label_count"] == 4
    assert "CABLE: CBL-0001" in output.read_text(encoding="utf-8")
    repeated = runner.invoke(app, ["labels", "export", "--output", str(output)])
    assert repeated.exit_code == 2
    assert output.read_text(encoding="utf-8") == render_label_csv(
        generate_label_manifest(_state(), project_name="Primary Reef System")
    )
    monkeypatch.chdir(tmp_path)
    default_export = runner.invoke(app, ["labels", "export"])
    expected = tmp_path / "reefproof-primary-reef-system-v0.1.2-labels.csv"
    assert default_export.exit_code == 0, default_export.stdout
    assert json.loads(default_export.stdout)["output"] == str(expected)
    assert expected.exists()
