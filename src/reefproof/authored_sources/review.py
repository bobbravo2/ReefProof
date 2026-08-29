"""Backend-authored semantic review of one normalized source import."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from reefproof.authored_sources.candidates import canonical_subject_id, record_candidate_values
from reefproof.authored_sources.models import AuthoredImportBatch, NormalizedSourceRecord
from reefproof.project_state import ProjectState


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ImportChangeState(StrEnum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"
    REMOVED_FROM_SOURCE = "REMOVED_FROM_SOURCE"


class ExternalIdentityBinding(_FrozenModel):
    binding_id: str
    project_id: str
    source_system: str = "google_sheets"
    source_instance: str
    namespace: str
    value: str
    canonical_subject_id: str
    import_batch_id: str | None = None
    evidence_reference: str | None = None
    rationale: str | None = None
    accepted_at: datetime

    @model_validator(mode="after")
    def require_source_evidence(self) -> ExternalIdentityBinding:
        if self.source_system == "google_sheets" and self.import_batch_id is None:
            raise ValueError("Google Sheets identity binding requires an import batch")
        if self.source_system != "google_sheets" and (
            self.evidence_reference is None or self.rationale is None
        ):
            raise ValueError("non-Sheet identity binding requires evidence and rationale")
        return self


class ImportFactChange(_FrozenModel):
    attribute: str
    proposed_value: str | None
    accepted_value: str | int | float | bool | None = None
    state: ImportChangeState


class ImportObjectReview(_FrozenModel):
    canonical_subject_id: str
    external_namespace: str
    external_id: str
    tab: str
    source_range: str | None
    state: ImportChangeState
    changes: tuple[ImportFactChange, ...]


class AuthoredImportReview(_FrozenModel):
    import_batch_id: str
    source_snapshot_hash: str
    valid: bool
    state_counts: dict[ImportChangeState, int]
    objects: tuple[ImportObjectReview, ...]


def _object_review(
    record: NormalizedSourceRecord,
    *,
    batch: AuthoredImportBatch,
    project_id: str,
    state: ProjectState,
    bindings: tuple[ExternalIdentityBinding, ...],
) -> ImportObjectReview:
    subject_id = canonical_subject_id(project_id, record)
    conflicting_binding = next(
        (
            binding
            for binding in bindings
            if binding.namespace == record.external_namespace
            and binding.value == record.external_id
            and binding.canonical_subject_id != subject_id
        ),
        None,
    )
    changes: list[ImportFactChange] = []
    for attribute, value in record_candidate_values(record):
        accepted = state.fact(subject_id, attribute)
        change_state = (
            ImportChangeState.NEW
            if accepted is None
            else ImportChangeState.UNCHANGED
            if accepted.value == value
            else ImportChangeState.CHANGED
        )
        if conflicting_binding is not None:
            change_state = ImportChangeState.CONFLICT
        changes.append(
            ImportFactChange(
                attribute=attribute,
                proposed_value=value,
                accepted_value=None if accepted is None else accepted.value,
                state=change_state,
            )
        )
    object_state = _highest_state(tuple(change.state for change in changes))
    return ImportObjectReview(
        canonical_subject_id=subject_id,
        external_namespace=record.external_namespace,
        external_id=record.external_id,
        tab=record.tab.value,
        source_range=record.provenance.source_range,
        state=object_state,
        changes=tuple(changes),
    )


def build_import_review(
    batch: AuthoredImportBatch,
    *,
    project_id: str,
    state: ProjectState,
    bindings: tuple[ExternalIdentityBinding, ...] = (),
    source_instance: str | None = None,
) -> AuthoredImportReview:
    """Compare one source batch to durable accepted state without mutating either."""

    if not batch.valid:
        objects = tuple(
            ImportObjectReview(
                canonical_subject_id=f"invalid:{diagnostic.tab.value}:{index}",
                external_namespace="",
                external_id="",
                tab=diagnostic.tab.value,
                source_range=diagnostic.source_range,
                state=ImportChangeState.INVALID,
                changes=(
                    ImportFactChange(
                        attribute=diagnostic.code,
                        proposed_value=diagnostic.message,
                        state=ImportChangeState.INVALID,
                    ),
                ),
            )
            for index, diagnostic in enumerate(batch.diagnostics, start=1)
        )
    else:
        objects = tuple(
            _object_review(
                record,
                batch=batch,
                project_id=project_id,
                state=state,
                bindings=bindings,
            )
            for record in batch.records
        )
        current_keys = {(record.external_namespace, record.external_id) for record in batch.records}
        for record in batch.records:
            fields = dict(record.fields)
            for namespace in ("DEVICE_ID", "PORT_ID", "CABLE_ID", "POWER_SUPPLY_ID"):
                value = fields.get(namespace, "")
                if value:
                    current_keys.add((namespace, value))
        removed = tuple(
            ImportObjectReview(
                canonical_subject_id=binding.canonical_subject_id,
                external_namespace=binding.namespace,
                external_id=binding.value,
                tab="",
                source_range=None,
                state=ImportChangeState.REMOVED_FROM_SOURCE,
                changes=(
                    ImportFactChange(
                        attribute="identity.external_id",
                        proposed_value=None,
                        accepted_value=binding.value,
                        state=ImportChangeState.REMOVED_FROM_SOURCE,
                    ),
                ),
            )
            for binding in bindings
            if (source_instance is None or binding.source_instance == source_instance)
            and (binding.namespace, binding.value) not in current_keys
        )
        objects = (*objects, *removed)
    counts = {change_state: 0 for change_state in ImportChangeState}
    for item in objects:
        counts[item.state] += 1
    return AuthoredImportReview(
        import_batch_id=batch.import_batch_id,
        source_snapshot_hash=batch.source_snapshot_hash,
        valid=batch.valid,
        state_counts=counts,
        objects=objects,
    )


def _highest_state(states: tuple[ImportChangeState, ...]) -> ImportChangeState:
    for state in (
        ImportChangeState.CONFLICT,
        ImportChangeState.INVALID,
        ImportChangeState.CHANGED,
        ImportChangeState.NEW,
        ImportChangeState.REMOVED_FROM_SOURCE,
        ImportChangeState.UNCHANGED,
    ):
        if state in states:
            return state
    return ImportChangeState.UNCHANGED
