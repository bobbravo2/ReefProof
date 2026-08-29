"""Explicit authored-versus-observed identity reconciliation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from reefproof.authored_sources.review import ExternalIdentityBinding
from reefproof.configuration import ConfigurationSnapshot
from reefproof.project_state import ProjectState


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReconciliationState(StrEnum):
    MATCHED = "MATCHED"
    AUTHORED_ONLY = "AUTHORED_ONLY"
    OBSERVED_ONLY = "OBSERVED_ONLY"
    CONFLICT = "CONFLICT"


class ReconciliationItem(_FrozenModel):
    reconciliation_id: str
    state: ReconciliationState
    canonical_subject_id: str | None = None
    authored_display_id: str | None = None
    observed_entity_id: str | None = None
    observed_vendor_id: str | None = None
    observed_display_name: str | None = None
    detail: str


class ReconciliationProjection(_FrozenModel):
    project_id: str
    observed_snapshot_hash: str | None = None
    observed_captured_at: str | None = None
    items: tuple[ReconciliationItem, ...]
    matched_count: int
    authored_only_count: int
    observed_only_count: int
    conflict_count: int

    @property
    def blocking_subject_ids(self) -> tuple[str, ...]:
        return tuple(
            item.canonical_subject_id
            for item in self.items
            if item.state is ReconciliationState.CONFLICT and item.canonical_subject_id is not None
        )


def reconciliation_projection(
    *,
    state: ProjectState,
    bindings: tuple[ExternalIdentityBinding, ...],
    observed_snapshot: ConfigurationSnapshot | None,
) -> ReconciliationProjection:
    """Project explicit identity bindings without guessing from names or topology."""

    authored = {
        fact.subject_id: str(fact.value)
        for fact in state.facts
        if f"rp:{state.project_id}:device:" in fact.subject_id
        and fact.attribute == "identity.external_id"
    }
    if observed_snapshot is not None and observed_snapshot.provenance != "OBSERVED":
        observed_snapshot = None
    observed = (
        {}
        if observed_snapshot is None
        else {entity.reefproof_id: entity for entity in observed_snapshot.entities}
    )
    observed_by_external: dict[str, list[str]] = {}
    for entity_id, entity in observed.items():
        for value in (entity.vendor_id, entity.reefproof_id):
            if value:
                observed_by_external.setdefault(value, []).append(entity_id)

    hydros_bindings = tuple(
        binding
        for binding in bindings
        if binding.source_system.casefold() == "hydros" and binding.canonical_subject_id in authored
    )
    bindings_by_subject: dict[str, list[ExternalIdentityBinding]] = {}
    for binding in hydros_bindings:
        bindings_by_subject.setdefault(binding.canonical_subject_id, []).append(binding)

    claimed_observed_ids: set[str] = set()
    items: list[ReconciliationItem] = []
    for subject_id, display_id in sorted(authored.items()):
        subject_bindings = bindings_by_subject.get(subject_id, [])
        matches = {
            entity_id
            for binding in subject_bindings
            for entity_id in observed_by_external.get(binding.value, [])
        }
        if len(matches) == 1:
            observed_id = next(iter(matches))
            entity = observed[observed_id]
            claimed_observed_ids.add(observed_id)
            items.append(
                ReconciliationItem(
                    reconciliation_id=f"authored:{subject_id}",
                    state=ReconciliationState.MATCHED,
                    canonical_subject_id=subject_id,
                    authored_display_id=display_id,
                    observed_entity_id=entity.reefproof_id,
                    observed_vendor_id=entity.vendor_id,
                    observed_display_name=entity.display_name,
                    detail="Explicit HYDROS identity binding matches one observed entity.",
                )
            )
        elif subject_bindings:
            items.append(
                ReconciliationItem(
                    reconciliation_id=f"authored:{subject_id}",
                    state=ReconciliationState.CONFLICT,
                    canonical_subject_id=subject_id,
                    authored_display_id=display_id,
                    detail=(
                        "Explicit HYDROS identity binding resolves to no observed entity."
                        if not matches
                        else "Explicit HYDROS identity binding resolves ambiguously."
                    ),
                )
            )
        else:
            items.append(
                ReconciliationItem(
                    reconciliation_id=f"authored:{subject_id}",
                    state=ReconciliationState.AUTHORED_ONLY,
                    canonical_subject_id=subject_id,
                    authored_display_id=display_id,
                    detail="No explicit HYDROS identity binding has been accepted.",
                )
            )

    for entity_id, entity in sorted(observed.items()):
        if entity_id in claimed_observed_ids:
            continue
        items.append(
            ReconciliationItem(
                reconciliation_id=f"observed:{entity_id}",
                state=ReconciliationState.OBSERVED_ONLY,
                observed_entity_id=entity_id,
                observed_vendor_id=entity.vendor_id,
                observed_display_name=entity.display_name,
                detail="Observed evidence is not explicitly bound to a canonical authored device.",
            )
        )

    counts = {item_state: 0 for item_state in ReconciliationState}
    for item in items:
        counts[item.state] += 1
    return ReconciliationProjection(
        project_id=state.project_id,
        observed_snapshot_hash=(
            None if observed_snapshot is None else observed_snapshot.snapshot_hash
        ),
        observed_captured_at=(
            None if observed_snapshot is None else observed_snapshot.captured_at.isoformat()
        ),
        items=tuple(items),
        matched_count=counts[ReconciliationState.MATCHED],
        authored_only_count=counts[ReconciliationState.AUTHORED_ONLY],
        observed_only_count=counts[ReconciliationState.OBSERVED_ONLY],
        conflict_count=counts[ReconciliationState.CONFLICT],
    )
