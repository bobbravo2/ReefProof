"""Pure trust-event and projection propagation models.

Trust is an overlay: canonical facts and raw evaluations remain immutable.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenTrustModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TrustScopeKind(StrEnum):
    EVIDENCE = "evidence"
    SUBSYSTEM = "subsystem"


class TrustStatus(StrEnum):
    TRUSTED = "TRUSTED"
    REVOKED = "REVOKED"


class TrustRootFact(FrozenTrustModel):
    subject_id: str
    attribute: str
    evidence_ids: tuple[str, ...]
    source_candidate_fact_id: str


class TrustEvent(FrozenTrustModel):
    trust_event_id: str = Field(pattern=r"^trust-[a-z0-9-]+$")
    project_id: str
    sequence: int = Field(gt=0)
    event_type: Literal["revoked", "restored"]
    occurred_at: datetime
    actor_id: str
    rationale: str = Field(min_length=1)
    scope_kind: TrustScopeKind
    scope_id: str
    affected_roots: tuple[TrustRootFact, ...]
    linked_revocation_id: str | None = None
    replacement_candidate_fact_ids: tuple[str, ...] = ()
    replacement_evidence_ids: tuple[str, ...] = ()
    totp_verified_at: datetime | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if not self.affected_roots:
            raise ValueError("trust event requires an immutable affected-root snapshot")
        if self.event_type == "revoked":
            if (
                self.linked_revocation_id is not None
                or self.replacement_candidate_fact_ids
                or self.replacement_evidence_ids
            ):
                raise ValueError("revocation cannot contain restoration material")
            if self.totp_verified_at is None:
                raise ValueError("revocation requires TOTP verification")
        elif self.linked_revocation_id is None or self.totp_verified_at is None:
            raise ValueError("restoration requires a linked revocation and TOTP verification")
        return self


class TrustState(FrozenTrustModel):
    project_id: str
    events: tuple[TrustEvent, ...]
    active_revocations: tuple[TrustEvent, ...]
    last_sequence: int


class ProjectionDependency(FrozenTrustModel):
    projection_id: str
    evidence_ids: tuple[str, ...] = ()
    subject_ids: tuple[str, ...] = ()
    projection_dependencies: tuple[str, ...] = ()


class EffectiveProjection(FrozenTrustModel):
    projection_id: str
    evaluated_state: str
    state: str
    trust_status: TrustStatus
    contributing_trust_event_ids: tuple[str, ...] = ()


def replay_trust(project_id: str, events: tuple[TrustEvent, ...]) -> TrustState:
    active: dict[str, TrustEvent] = {}
    expected = 1
    seen: set[str] = set()
    for event in events:
        if event.project_id != project_id or event.sequence != expected:
            raise ValueError("trust stream must be project-bound and contiguous")
        if event.trust_event_id in seen:
            raise ValueError("duplicate trust event identity")
        seen.add(event.trust_event_id)
        expected += 1
        if event.event_type == "revoked":
            if any(
                item.scope_kind == event.scope_kind and item.scope_id == event.scope_id
                for item in active.values()
            ):
                raise ValueError("duplicate active revocation")
            active[event.trust_event_id] = event
        else:
            linked = active.get(event.linked_revocation_id or "")
            if linked is None:
                raise ValueError("restoration does not link an active revocation")
            if (
                linked.scope_kind != event.scope_kind
                or linked.scope_id != event.scope_id
                or linked.affected_roots != event.affected_roots
            ):
                raise ValueError("restoration does not match its revocation")
            del active[linked.trust_event_id]
    return TrustState(
        project_id=project_id,
        events=events,
        active_revocations=tuple(active.values()),
        last_sequence=len(events),
    )


def revoked_projection_ids(
    declarations: tuple[ProjectionDependency, ...],
    revocations: tuple[TrustEvent, ...],
) -> tuple[str, ...]:
    """Return deterministic downstream closure; invalid graphs fail closed."""

    by_id = {item.projection_id: item for item in declarations}
    if len(by_id) != len(declarations):
        raise ValueError("duplicate projection identity")
    for item in declarations:
        if any(dependency not in by_id for dependency in item.projection_dependencies):
            raise ValueError("unknown projection dependency")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(projection_id: str) -> None:
        if projection_id in visiting:
            raise ValueError("projection dependency cycle")
        if projection_id in visited:
            return
        visiting.add(projection_id)
        for dependency in by_id[projection_id].projection_dependencies:
            visit(dependency)
        visiting.remove(projection_id)
        visited.add(projection_id)

    for projection_id in sorted(by_id):
        visit(projection_id)

    seeds: set[str] = set()
    for declaration in declarations:
        for event in revocations:
            if event.scope_kind is TrustScopeKind.EVIDENCE:
                if event.scope_id in declaration.evidence_ids:
                    seeds.add(declaration.projection_id)
            elif event.scope_id in declaration.subject_ids:
                seeds.add(declaration.projection_id)
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        for declaration in declarations:
            if declaration.projection_id not in affected and any(
                dep in affected for dep in declaration.projection_dependencies
            ):
                affected.add(declaration.projection_id)
                changed = True
    return tuple(sorted(affected))


def apply_trust(
    *,
    declaration: ProjectionDependency,
    evaluated_state: str,
    active_revocations: tuple[TrustEvent, ...],
    declarations: tuple[ProjectionDependency, ...],
) -> EffectiveProjection:
    affected = declaration.projection_id in revoked_projection_ids(declarations, active_revocations)
    event_ids = tuple(
        event.trust_event_id
        for event in active_revocations
        if (
            event.scope_id in declaration.evidence_ids
            or event.scope_id in declaration.subject_ids
            or affected
        )
    )
    return EffectiveProjection(
        projection_id=declaration.projection_id,
        evaluated_state=evaluated_state,
        state="UNKNOWN" if affected else evaluated_state,
        trust_status=TrustStatus.REVOKED if affected else TrustStatus.TRUSTED,
        contributing_trust_event_ids=event_ids if affected else (),
    )
