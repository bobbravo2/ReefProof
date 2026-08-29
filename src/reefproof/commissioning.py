"""Evidence-backed commissioning records and deterministic device posture."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reefproof.authored_sources.review import ExternalIdentityBinding
from reefproof.labels import LabelKind, LabelManifest
from reefproof.project_state import ProjectState


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EvidenceState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CommissioningState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMMISSIONED = "COMMISSIONED"
    REVOKED = "REVOKED"


class VerificationKind(StrEnum):
    CONNECTION = "CONNECTION"
    POWER = "POWER"
    COMMUNICATIONS = "COMMUNICATIONS"
    FAULT_TEST = "FAULT_TEST"
    LABEL = "LABEL"


class VerificationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class LabelEndpoint(StrEnum):
    ITEM = "ITEM"
    FROM = "FROM"
    TO = "TO"


class CommissioningVerification(_FrozenModel):
    verification_id: str
    project_id: str
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
    verified_by_actor_id: str
    verified_at: datetime

    @model_validator(mode="after")
    def validate_shape(self) -> CommissioningVerification:
        if self.verified_at.utcoffset() is None:
            raise ValueError("verification timestamp must be timezone-aware")
        if self.kind is VerificationKind.LABEL:
            if self.manifest_id is None or self.label_id is None or self.label_endpoint is None:
                raise ValueError(
                    "label verification requires manifest, label, and endpoint identity"
                )
        elif any(
            item is not None for item in (self.manifest_id, self.label_id, self.label_endpoint)
        ):
            raise ValueError("only label verification may carry label identity")
        if self.kind is VerificationKind.CONNECTION:
            if self.connection_id is None:
                raise ValueError("connection verification requires canonical connection identity")
        elif self.connection_id is not None:
            raise ValueError("only connection verification may carry connection identity")
        if self.kind is VerificationKind.FAULT_TEST and self.control_surface_id is None:
            raise ValueError("fault-test verification requires a control surface")
        if self.kind is not VerificationKind.FAULT_TEST and self.control_surface_id is not None:
            raise ValueError("only fault-test verification may carry a control surface")
        return self


class FailureModeDispositionKind(StrEnum):
    ACCEPTED_RISK = "ACCEPTED_RISK"
    ALERTED_DETECTED = "ALERTED_DETECTED"
    AUTOMATED_MITIGATION = "AUTOMATED_MITIGATION"


class FailureModeDisposition(_FrozenModel):
    disposition_id: str
    project_id: str
    device_id: str
    failure_mode_id: str
    disposition: FailureModeDispositionKind
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    decided_by_actor_id: str
    decided_at: datetime

    @model_validator(mode="after")
    def require_absolute_time(self) -> FailureModeDisposition:
        if self.decided_at.utcoffset() is None:
            raise ValueError("failure-mode disposition timestamp must be timezone-aware")
        return self


class CommissioningRequirement(_FrozenModel):
    requirement_id: str
    label: str
    state: EvidenceState
    detail: str
    evidence_ids: tuple[str, ...] = ()


class CommissioningDevice(_FrozenModel):
    device_id: str
    canonical_device_id: str
    display_name: str
    state: CommissioningState
    requirements: tuple[CommissioningRequirement, ...]
    next_action: str | None


class CommissioningProjection(_FrozenModel):
    project_id: str
    devices: tuple[CommissioningDevice, ...]
    commissioned_count: int
    blocked_count: int
    unknown_requirement_count: int


def _latest_verifications(
    records: tuple[CommissioningVerification, ...],
) -> dict[tuple[str, VerificationKind, str, str], CommissioningVerification]:
    latest: dict[tuple[str, VerificationKind, str, str], CommissioningVerification] = {}
    for record in sorted(records, key=lambda item: (item.verified_at, item.verification_id)):
        key = (
            record.device_id,
            record.kind,
            record.connection_id or record.control_surface_id or "",
            f"{record.label_id or ''}:{record.label_endpoint or ''}",
        )
        latest[key] = record
    return latest


def _verification_requirement(
    *,
    requirement_id: str,
    label: str,
    record: CommissioningVerification | None,
    missing_detail: str,
) -> CommissioningRequirement:
    if record is None:
        return CommissioningRequirement(
            requirement_id=requirement_id,
            label=label,
            state=EvidenceState.UNKNOWN,
            detail=missing_detail,
        )
    return CommissioningRequirement(
        requirement_id=requirement_id,
        label=label,
        state=(
            EvidenceState.FAIL if record.outcome is VerificationOutcome.FAIL else EvidenceState.PASS
        ),
        detail=record.rationale,
        evidence_ids=(record.evidence_reference,),
    )


def commissioning_projection(
    *,
    state: ProjectState,
    bindings: tuple[ExternalIdentityBinding, ...],
    label_manifest: LabelManifest,
    verifications: tuple[CommissioningVerification, ...],
    dispositions: tuple[FailureModeDisposition, ...],
    blocking_conflict_subject_ids: tuple[str, ...] = (),
) -> CommissioningProjection:
    """Derive commissioning only from accepted identity and explicit proof."""

    facts_by_subject: dict[str, dict[str, str]] = {}
    for fact in state.facts:
        if isinstance(fact.value, str):
            facts_by_subject.setdefault(fact.subject_id, {})[fact.attribute] = fact.value
    devices = {
        subject_id: facts
        for subject_id, facts in facts_by_subject.items()
        if f"rp:{state.project_id}:device:" in subject_id
    }
    latest = _latest_verifications(verifications)
    projected: list[CommissioningDevice] = []
    for device_id, facts in sorted(devices.items()):
        display = facts.get("identity.external_id", device_id.rsplit(":", 1)[-1])
        bound = any(binding.canonical_subject_id == device_id for binding in bindings)
        requirements: list[CommissioningRequirement] = [
            CommissioningRequirement(
                requirement_id="identity",
                label="Inventory identity",
                state=(
                    EvidenceState.PASS
                    if bound and bool(facts.get("device.location"))
                    else EvidenceState.UNKNOWN
                ),
                detail=(
                    "Canonical identity, source binding, and location are accepted."
                    if bound and bool(facts.get("device.location"))
                    else "Accepted source identity binding and physical location are required."
                ),
            )
        ]
        related_cables = {
            subject_id: cable_facts
            for subject_id, cable_facts in facts_by_subject.items()
            if f"rp:{state.project_id}:cable:" in subject_id
            and (
                cable_facts.get("connection.device_id") == display
                or display
                in {
                    cable_facts.get("connection.from_device"),
                    cable_facts.get("connection.to_device"),
                }
            )
        }
        connection_complete = bool(related_cables) and all(
            all(
                cable.get(f"connection.{field}")
                for field in (
                    "from_zone",
                    "from_device",
                    "from_port",
                    "to_zone",
                    "to_device",
                    "to_port",
                )
            )
            for cable in related_cables.values()
        )
        connection_verifications = tuple(
            latest.get((device_id, VerificationKind.CONNECTION, cable_id, ":"))
            for cable_id in related_cables
        )
        connection_failed = any(
            record is not None and record.outcome is VerificationOutcome.FAIL
            for record in connection_verifications
        )
        connection_verified = (
            connection_complete
            and bool(connection_verifications)
            and all(
                record is not None and record.outcome is VerificationOutcome.PASS
                for record in connection_verifications
            )
        )
        requirements.append(
            CommissioningRequirement(
                requirement_id="connections",
                label="Physical connection verification",
                state=(
                    EvidenceState.FAIL
                    if connection_failed
                    else EvidenceState.PASS
                    if connection_verified
                    else EvidenceState.UNKNOWN
                ),
                detail=(
                    "Every accepted removable connection has complete endpoints and physical proof."
                    if connection_verified
                    else "Physical connection evidence contradicts the accepted topology."
                    if connection_failed
                    else (
                        "Complete accepted FROM/TO endpoints and physical connection proof "
                        "are required."
                    )
                ),
                evidence_ids=tuple(
                    record.evidence_reference
                    for record in connection_verifications
                    if record is not None
                ),
            )
        )
        electrical_known = bool(facts.get("device.power_domain_id")) and connection_complete
        requirements.append(
            CommissioningRequirement(
                requirement_id="electrical-inventory",
                label="Electrical inventory completeness",
                state=EvidenceState.PASS if electrical_known else EvidenceState.UNKNOWN,
                detail=(
                    "Accepted device power-domain and connection evidence are present."
                    if electrical_known
                    else "Accepted power-domain and physical connection evidence are required."
                ),
            )
        )
        required_labels = [
            (record.label_id, LabelEndpoint.ITEM)
            for record in label_manifest.records
            if record.label_kind is LabelKind.DEVICE and record.canonical_subject_id == device_id
        ]
        related_ports = {
            subject_id
            for subject_id, port_facts in facts_by_subject.items()
            if f"rp:{state.project_id}:port:" in subject_id
            and port_facts.get("port.device_id") == display
        }
        required_labels.extend(
            (record.label_id, LabelEndpoint.ITEM)
            for record in label_manifest.records
            if record.label_kind is LabelKind.PORT and record.canonical_subject_id in related_ports
        )
        for cable_id in related_cables:
            required_labels.extend(
                (record.label_id, endpoint)
                for record in label_manifest.records
                if record.label_kind is LabelKind.CABLE and record.canonical_subject_id == cable_id
                for endpoint in (LabelEndpoint.FROM, LabelEndpoint.TO)
            )
        label_records = [
            latest.get((device_id, VerificationKind.LABEL, "", f"{label_id}:{endpoint}"))
            for label_id, endpoint in required_labels
        ]
        labels_complete = bool(required_labels) and all(
            record is not None and record.outcome is VerificationOutcome.PASS
            for record in label_records
        )
        labels_failed = any(
            record is not None and record.outcome is VerificationOutcome.FAIL
            for record in label_records
        )
        required_label_keys = {
            (label_manifest.manifest_id, label_id, endpoint)
            for label_id, endpoint in required_labels
        }
        labels_failed = labels_failed or any(
            record.device_id == device_id
            and record.kind is VerificationKind.LABEL
            and (record.manifest_id, record.label_id, record.label_endpoint)
            not in required_label_keys
            for record in verifications
        )
        requirements.append(
            CommissioningRequirement(
                requirement_id="labels",
                label="Physical label completeness",
                state=(
                    EvidenceState.FAIL
                    if labels_failed
                    else EvidenceState.PASS
                    if labels_complete
                    else EvidenceState.UNKNOWN
                ),
                detail=(
                    "Device and both cable endpoints are physically label-verified."
                    if labels_complete
                    else "Device and both removable-cable endpoint labels require verification."
                ),
                evidence_ids=tuple(
                    record.evidence_reference for record in label_records if record is not None
                ),
            )
        )
        for kind, label, missing in (
            (VerificationKind.POWER, "Power verification", "Power evidence is missing."),
            (
                VerificationKind.COMMUNICATIONS,
                "Communications verification",
                "Communications evidence or an explicit N/A reason is missing.",
            ),
        ):
            requirements.append(
                _verification_requirement(
                    requirement_id=kind.value.casefold(),
                    label=label,
                    record=latest.get((device_id, kind, "", ":")),
                    missing_detail=missing,
                )
            )
        output_surfaces = tuple(
            subject_id
            for subject_id, output_facts in facts_by_subject.items()
            if f"rp:{state.project_id}:output:" in subject_id
            and output_facts.get("output.device_id") == display
        )
        fault_records = [
            latest.get((device_id, VerificationKind.FAULT_TEST, surface, ":"))
            for surface in output_surfaces
        ]
        fault_complete = bool(output_surfaces) and all(
            record is not None and record.outcome is not VerificationOutcome.FAIL
            for record in fault_records
        )
        fault_failed = any(
            record is not None and record.outcome is VerificationOutcome.FAIL
            for record in fault_records
        )
        requirements.append(
            CommissioningRequirement(
                requirement_id="fault-tests",
                label="Bounded fault-test completeness",
                state=(
                    EvidenceState.FAIL
                    if fault_failed
                    else EvidenceState.PASS
                    if fault_complete
                    else EvidenceState.UNKNOWN
                ),
                detail=(
                    "Every authored control surface has bounded fault-test evidence."
                    if fault_complete
                    else "Every authored control surface requires bounded fault-test evidence."
                ),
            )
        )
        required_failure_modes = {"power_loss"}
        if output_surfaces:
            required_failure_modes.add("control_link_loss")
        if any(
            token in facts.get("device.item_name", "").casefold()
            for token in ("pump", "valve", "skimmer", "reactor")
        ):
            required_failure_modes.add("leak_or_flow_loss")
        disposition_by_mode = {
            item.failure_mode_id: item for item in dispositions if item.device_id == device_id
        }
        disposition_complete = required_failure_modes.issubset(disposition_by_mode)
        requirements.append(
            CommissioningRequirement(
                requirement_id="failure-modes",
                label="Failure-mode dispositions",
                state=EvidenceState.PASS if disposition_complete else EvidenceState.UNKNOWN,
                detail=(
                    "Every registered applicable failure mode has an explicit disposition."
                    if disposition_complete
                    else (
                        "Power loss and applicable control-link/leak-risk modes require "
                        "dispositions."
                    )
                ),
            )
        )
        requirements.append(
            CommissioningRequirement(
                requirement_id="contradictions",
                label="Blocking contradictions",
                state=(
                    EvidenceState.FAIL
                    if device_id in blocking_conflict_subject_ids
                    else EvidenceState.PASS
                ),
                detail=(
                    "A source or evidence contradiction blocks commissioning."
                    if device_id in blocking_conflict_subject_ids
                    else "No blocking contradiction is recorded."
                ),
            )
        )
        states = {item.state for item in requirements}
        evidence_count = sum(bool(item.evidence_ids) for item in requirements)
        device_state = (
            CommissioningState.BLOCKED
            if EvidenceState.FAIL in states
            else CommissioningState.COMMISSIONED
            if states == {EvidenceState.PASS}
            else CommissioningState.IN_PROGRESS
            if evidence_count or EvidenceState.PASS in states
            else CommissioningState.NOT_STARTED
        )
        next_requirement = next(
            (item for item in requirements if item.state is not EvidenceState.PASS), None
        )
        projected.append(
            CommissioningDevice(
                device_id=display,
                canonical_device_id=device_id,
                display_name=display,
                state=device_state,
                requirements=tuple(requirements),
                next_action=None if next_requirement is None else next_requirement.detail,
            )
        )
    return CommissioningProjection(
        project_id=state.project_id,
        devices=tuple(projected),
        commissioned_count=sum(item.state is CommissioningState.COMMISSIONED for item in projected),
        blocked_count=sum(item.state is CommissioningState.BLOCKED for item in projected),
        unknown_requirement_count=sum(
            requirement.state is EvidenceState.UNKNOWN
            for item in projected
            for requirement in item.requirements
        ),
    )
