from __future__ import annotations

from datetime import UTC, datetime

from reefproof.authored_sources import ExternalIdentityBinding
from reefproof.commissioning import (
    CommissioningState,
    CommissioningVerification,
    FailureModeDisposition,
    FailureModeDispositionKind,
    LabelEndpoint,
    VerificationKind,
    VerificationOutcome,
    commissioning_projection,
)
from reefproof.labels import generate_label_manifest
from reefproof.project_state import CanonicalFact, ProjectState

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
PROJECT_ID = "primary-reef-system"
DEVICE = f"rp:{PROJECT_ID}:device:dev-1"
PORT = f"rp:{PROJECT_ID}:port:port-1"
CABLE = f"rp:{PROJECT_ID}:cable:cbl-0001"
OUTPUT = f"rp:{PROJECT_ID}:output:out-1"


def _fact(subject: str, attribute: str, value: str, index: int) -> CanonicalFact:
    return CanonicalFact(
        subject_id=subject,
        attribute=attribute,
        value=value,
        source_candidate_fact_id=f"candidate-{index}",
        accepted_by_actor_id="local-acceptance-authority",
        accepted_at=NOW,
        evidence_ids=("evidence-source-fixture",),
    )


def _state() -> ProjectState:
    values = (
        (DEVICE, "identity.external_id", "DEV-1"),
        (DEVICE, "device.location", "Sump"),
        (DEVICE, "device.power_domain_id", "PD-1"),
        (PORT, "identity.external_id", "PORT-1"),
        (PORT, "port.device_id", "DEV-1"),
        (CABLE, "identity.external_id", "CBL-0001"),
        (CABLE, "connection.cable_id", "CBL-0001"),
        (CABLE, "connection.device_id", "DEV-1"),
        (CABLE, "connection.from_zone", "Cabinet"),
        (CABLE, "connection.from_device", "Controller"),
        (CABLE, "connection.from_port", "Output 1"),
        (CABLE, "connection.to_zone", "Sump"),
        (CABLE, "connection.to_device", "DEV-1"),
        (CABLE, "connection.to_port", "Power"),
        (OUTPUT, "output.device_id", "DEV-1"),
    )
    return ProjectState(
        project_id=PROJECT_ID,
        facts=tuple(
            _fact(subject, attribute, value, index)
            for index, (subject, attribute, value) in enumerate(values, start=1)
        ),
        last_sequence=len(values),
    )


def _binding() -> ExternalIdentityBinding:
    return ExternalIdentityBinding(
        binding_id="binding-device",
        project_id=PROJECT_ID,
        source_instance="sheet-fixture",
        namespace="DEVICE_ID",
        value="DEV-1",
        canonical_subject_id=DEVICE,
        import_batch_id="import-fixture",
        accepted_at=NOW,
    )


def _verification(
    suffix: str,
    kind: VerificationKind,
    *,
    outcome: VerificationOutcome = VerificationOutcome.PASS,
    connection_id: str | None = None,
    control_surface_id: str | None = None,
    manifest_id: str | None = None,
    label_id: str | None = None,
    label_endpoint: LabelEndpoint | None = None,
) -> CommissioningVerification:
    return CommissioningVerification(
        verification_id=f"verification-{suffix}",
        project_id=PROJECT_ID,
        device_id=DEVICE,
        kind=kind,
        outcome=outcome,
        rationale=f"Verified {suffix}",
        evidence_reference=f"evidence-{suffix}",
        connection_id=connection_id,
        control_surface_id=control_surface_id,
        manifest_id=manifest_id,
        label_id=label_id,
        label_endpoint=label_endpoint,
        verified_by_actor_id="local-acceptance-authority",
        verified_at=NOW,
    )


def test_commissioning_stays_unknown_until_every_applicable_proof_exists() -> None:
    state = _state()
    manifest = generate_label_manifest(state, project_name="Primary Reef System")
    initial = commissioning_projection(
        state=state,
        bindings=(_binding(),),
        label_manifest=manifest,
        verifications=(),
        dispositions=(),
    )
    device = initial.devices[0]
    assert device.state is CommissioningState.IN_PROGRESS
    assert {item.requirement_id for item in device.requirements if item.state == "UNKNOWN"} == {
        "labels",
        "connections",
        "power",
        "communications",
        "fault-tests",
        "failure-modes",
    }

    device_label = next(record for record in manifest.records if record.label_kind == "DEVICE")
    port_label = next(record for record in manifest.records if record.label_kind == "PORT")
    cable_label = next(record for record in manifest.records if record.label_kind == "CABLE")
    verifications = (
        _verification("connection", VerificationKind.CONNECTION, connection_id=CABLE),
        _verification("power", VerificationKind.POWER),
        _verification(
            "communications-na",
            VerificationKind.COMMUNICATIONS,
            outcome=VerificationOutcome.NOT_APPLICABLE,
        ),
        _verification("fault", VerificationKind.FAULT_TEST, control_surface_id=OUTPUT),
        _verification(
            "device-label",
            VerificationKind.LABEL,
            manifest_id=manifest.manifest_id,
            label_id=device_label.label_id,
            label_endpoint=LabelEndpoint.ITEM,
        ),
        _verification(
            "port-label",
            VerificationKind.LABEL,
            manifest_id=manifest.manifest_id,
            label_id=port_label.label_id,
            label_endpoint=LabelEndpoint.ITEM,
        ),
        _verification(
            "cable-from",
            VerificationKind.LABEL,
            manifest_id=manifest.manifest_id,
            label_id=cable_label.label_id,
            label_endpoint=LabelEndpoint.FROM,
        ),
        _verification(
            "cable-to",
            VerificationKind.LABEL,
            manifest_id=manifest.manifest_id,
            label_id=cable_label.label_id,
            label_endpoint=LabelEndpoint.TO,
        ),
    )
    dispositions = tuple(
        FailureModeDisposition(
            disposition_id=f"disposition-{mode}",
            project_id=PROJECT_ID,
            device_id=DEVICE,
            failure_mode_id=mode,
            disposition=FailureModeDispositionKind.ALERTED_DETECTED,
            rationale=f"Reviewed {mode}",
            evidence_reference=f"evidence-{mode}",
            decided_by_actor_id="local-acceptance-authority",
            decided_at=NOW,
        )
        for mode in ("power_loss", "control_link_loss")
    )
    complete = commissioning_projection(
        state=state,
        bindings=(_binding(),),
        label_manifest=manifest,
        verifications=verifications,
        dispositions=dispositions,
    )
    assert complete.devices[0].state is CommissioningState.COMMISSIONED
    assert all(item.state == "PASS" for item in complete.devices[0].requirements)


def test_device_without_authored_control_surface_keeps_fault_tests_unknown() -> None:
    state = _state()
    facts = tuple(fact for fact in state.facts if fact.subject_id != OUTPUT)
    state = state.model_copy(update={"facts": facts, "last_sequence": len(facts)})
    manifest = generate_label_manifest(state, project_name="Primary Reef System")

    projection = commissioning_projection(
        state=state,
        bindings=(_binding(),),
        label_manifest=manifest,
        verifications=(),
        dispositions=(),
    )

    device = projection.devices[0]
    fault_tests = next(
        requirement
        for requirement in device.requirements
        if requirement.requirement_id == "fault-tests"
    )
    assert fault_tests.state == "UNKNOWN"
    assert device.state is CommissioningState.IN_PROGRESS


def test_wrong_label_identity_blocks_commissioning() -> None:
    state = _state()
    manifest = generate_label_manifest(state, project_name="Primary Reef System")
    wrong = _verification(
        "wrong-label",
        VerificationKind.LABEL,
        manifest_id=manifest.manifest_id,
        label_id="cable:wrong",
        label_endpoint=LabelEndpoint.FROM,
    )
    projection = commissioning_projection(
        state=state,
        bindings=(_binding(),),
        label_manifest=manifest,
        verifications=(wrong,),
        dispositions=(),
    )
    assert projection.devices[0].state is CommissioningState.BLOCKED
    labels = next(
        item for item in projection.devices[0].requirements if item.requirement_id == "labels"
    )
    assert labels.state == "FAIL"
