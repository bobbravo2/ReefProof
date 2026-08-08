"""Deterministic, no-LLM Overview projection for ADR 0003."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reefproof.information_architecture import OverviewSection
from reefproof.project_state import CanonicalFact, ProjectState
from reefproof.recommendations import (
    DomainReference,
    EvidenceStatus,
    ReasonCode,
    RecommendedAction,
    select_recommended_action,
)
from reefproof.trust import TrustState, TrustStatus


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BriefReasonCode(StrEnum):
    RECOMMENDATION_SELECTED = "recommendation_selected"
    NO_RECOMMENDATION = "no_recommendation"
    POSTURE_FROM_ACCEPTED_FACT = "posture_from_accepted_fact"
    POSTURE_NOT_ESTABLISHED = "posture_not_established"
    POSTURE_VALUE_UNRECOGNIZED = "posture_value_unrecognized"
    RULE_RISK = "rule_risk"
    REQUIRED_KNOWLEDGE_MISSING = "required_knowledge_missing"
    ACCEPTED_DECISION = "accepted_decision"
    CANONICAL_MAP_PROJECTION = "canonical_map_projection"
    STRUCTURED_UNKNOWNS_AVAILABLE = "structured_unknowns_available"
    NO_STRUCTURED_UNKNOWNS = "no_structured_unknowns"


class ProvenanceKind(StrEnum):
    ACCEPTED_FACT = "accepted_fact"
    INVARIANT_RESULT = "invariant_result"
    STRUCTURED_UNKNOWN = "structured_unknown"
    PROJECT_STATE = "project_state"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    BLOCKER = "blocker"


class ProjectionProvenance(FrozenModel):
    kind: ProvenanceKind
    source_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    evidence_status: EvidenceStatus | None = None


class RecommendationStatus(StrEnum):
    SELECTED = "SELECTED"
    UNKNOWN = "UNKNOWN"


class RecommendationProjection(FrozenModel):
    status: RecommendationStatus
    action: RecommendedAction | None
    reason_codes: tuple[BriefReasonCode, ...] = Field(min_length=1)
    provenance: tuple[ProjectionProvenance, ...]

    @model_validator(mode="after")
    def match_status_and_action(self) -> Self:
        if (self.status is RecommendationStatus.SELECTED) != (self.action is not None):
            raise ValueError("SELECTED requires exactly one action; UNKNOWN requires none")
        return self


class ProjectPosture(StrEnum):
    COMMISSIONING = "commissioning"
    OPERATIONAL = "operational"
    UNKNOWN = "UNKNOWN"


class PostureProjection(FrozenModel):
    posture: ProjectPosture
    evaluated_posture: ProjectPosture
    trust_status: TrustStatus
    contributing_trust_event_ids: tuple[str, ...] = ()
    reason_codes: tuple[BriefReasonCode, ...] = Field(min_length=1)
    provenance: tuple[ProjectionProvenance, ...]


class RiskSeverity(IntEnum):
    CRITICAL = 1
    HIGH = 2
    WARNING = 3
    INFO = 4


class RiskProjection(FrozenModel):
    risk_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    severity: RiskSeverity
    affected_objects: tuple[DomainReference, ...] = Field(min_length=1)
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    provenance: tuple[ProjectionProvenance, ...] = Field(min_length=1)


class UnknownImpact(IntEnum):
    CATASTROPHIC = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class UnknownProjection(FrozenModel):
    unknown_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    impact: UnknownImpact
    affected_objects: tuple[DomainReference, ...] = Field(min_length=1)
    reason_codes: tuple[BriefReasonCode, ...] = (BriefReasonCode.REQUIRED_KNOWLEDGE_MISSING,)
    provenance: tuple[ProjectionProvenance, ...] = Field(min_length=1)


class AcceptedDecisionProjection(FrozenModel):
    subject_id: str
    attribute: str
    accepted_value: str | int | float | bool
    accepted_by_actor_id: str
    accepted_at: datetime
    source_candidate_fact_id: str
    reason_codes: tuple[BriefReasonCode, ...] = (BriefReasonCode.ACCEPTED_DECISION,)
    provenance: tuple[ProjectionProvenance, ...] = Field(min_length=1)


class CompactMapReference(FrozenModel):
    route: str = Field(pattern=r"^/projects/[a-z][a-z0-9_-]*/system-map$")
    reason_codes: tuple[BriefReasonCode, ...] = (BriefReasonCode.CANONICAL_MAP_PROJECTION,)
    provenance: tuple[ProjectionProvenance, ...] = Field(min_length=1)


class ContinueInterviewReference(FrozenModel):
    route: str = Field(pattern=r"^/projects/[a-z][a-z0-9_-]*/sessions/continue-interview$")
    reason_codes: tuple[BriefReasonCode, ...] = Field(min_length=1)
    based_on_unknown_ids: tuple[str, ...]
    provenance: tuple[ProjectionProvenance, ...] = Field(min_length=1)


class ProjectBrief(FrozenModel):
    """Typed projection in the exact accepted Overview order."""

    project_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    sections: tuple[OverviewSection, ...]
    recommended_next_action: RecommendationProjection
    current_posture: PostureProjection
    highest_consequence_risks: tuple[RiskProjection, ...]
    important_unknowns: tuple[UnknownProjection, ...]
    recent_accepted_decisions: tuple[AcceptedDecisionProjection, ...]
    compact_system_map: CompactMapReference
    continue_interview: ContinueInterviewReference

    @model_validator(mode="after")
    def require_exact_overview_order(self) -> Self:
        if self.sections != tuple(OverviewSection):
            raise ValueError("project brief sections must use the accepted Overview order")
        return self


def project_brief(
    *,
    state: ProjectState,
    actions: tuple[RecommendedAction, ...] = (),
    risks: tuple[RiskProjection, ...] = (),
    unknowns: tuple[UnknownProjection, ...] = (),
    risk_limit: int = 3,
    unknown_limit: int = 5,
    decision_limit: int = 5,
    trust: TrustState | None = None,
) -> ProjectBrief:
    """Project one deterministic Overview from canonical and derived state."""

    for label, value in (
        ("risk_limit", risk_limit),
        ("unknown_limit", unknown_limit),
        ("decision_limit", decision_limit),
    ):
        if value < 0:
            raise ValueError(f"{label} cannot be negative")

    selected = select_recommended_action(actions)
    recommendation = (
        RecommendationProjection(
            status=RecommendationStatus.UNKNOWN,
            action=None,
            reason_codes=(BriefReasonCode.NO_RECOMMENDATION,),
            provenance=(_state_provenance(state),),
        )
        if selected is None
        else RecommendationProjection(
            status=RecommendationStatus.SELECTED,
            action=selected,
            reason_codes=(BriefReasonCode.RECOMMENDATION_SELECTED,),
            provenance=_recommendation_provenance(selected, state),
        )
    )

    ordered_risks = tuple(
        sorted(risks, key=lambda risk: (risk.severity, risk.risk_id))[:risk_limit]
    )
    ordered_unknowns = tuple(
        sorted(unknowns, key=lambda unknown: (unknown.impact, unknown.unknown_id))[:unknown_limit]
    )
    decision_facts = sorted(
        state.facts,
        key=lambda fact: (
            -fact.accepted_at.timestamp(),
            fact.subject_id,
            fact.attribute,
            fact.source_candidate_fact_id,
        ),
    )[:decision_limit]

    posture = _project_posture(state)
    phase_fact = state.fact(state.project_id, "project.phase")
    if trust is not None and phase_fact is not None:
        contributors = tuple(
            event.trust_event_id
            for event in trust.active_revocations
            if (
                (event.scope_kind.value == "evidence" and event.scope_id in phase_fact.evidence_ids)
                or (
                    event.scope_kind.value == "subsystem"
                    and event.scope_id == phase_fact.subject_id
                )
            )
        )
        if contributors:
            posture = posture.model_copy(
                update={
                    "posture": ProjectPosture.UNKNOWN,
                    "trust_status": TrustStatus.REVOKED,
                    "contributing_trust_event_ids": contributors,
                }
            )

    return ProjectBrief(
        project_id=state.project_id,
        sections=tuple(OverviewSection),
        recommended_next_action=recommendation,
        current_posture=posture,
        highest_consequence_risks=ordered_risks,
        important_unknowns=ordered_unknowns,
        recent_accepted_decisions=tuple(_decision_projection(fact) for fact in decision_facts),
        compact_system_map=CompactMapReference(
            route=f"/projects/{state.project_id}/system-map",
            provenance=(_state_provenance(state),),
        ),
        continue_interview=ContinueInterviewReference(
            route=f"/projects/{state.project_id}/sessions/continue-interview",
            reason_codes=(
                BriefReasonCode.STRUCTURED_UNKNOWNS_AVAILABLE
                if ordered_unknowns
                else BriefReasonCode.NO_STRUCTURED_UNKNOWNS,
            ),
            based_on_unknown_ids=tuple(unknown.unknown_id for unknown in ordered_unknowns),
            provenance=(
                tuple(source for unknown in ordered_unknowns for source in unknown.provenance)
                or (_state_provenance(state),)
            ),
        ),
    )


def _project_posture(state: ProjectState) -> PostureProjection:
    phase_fact = state.fact(state.project_id, "project.phase")
    if phase_fact is None:
        return PostureProjection(
            posture=ProjectPosture.UNKNOWN,
            evaluated_posture=ProjectPosture.UNKNOWN,
            trust_status=TrustStatus.TRUSTED,
            reason_codes=(BriefReasonCode.POSTURE_NOT_ESTABLISHED,),
            provenance=(_state_provenance(state),),
        )
    provenance = (_fact_provenance(phase_fact),)
    try:
        posture = ProjectPosture(phase_fact.value)
    except (TypeError, ValueError):
        return PostureProjection(
            posture=ProjectPosture.UNKNOWN,
            evaluated_posture=ProjectPosture.UNKNOWN,
            trust_status=TrustStatus.TRUSTED,
            reason_codes=(BriefReasonCode.POSTURE_VALUE_UNRECOGNIZED,),
            provenance=provenance,
        )
    if posture is ProjectPosture.UNKNOWN:
        return PostureProjection(
            posture=posture,
            evaluated_posture=posture,
            trust_status=TrustStatus.TRUSTED,
            reason_codes=(BriefReasonCode.POSTURE_VALUE_UNRECOGNIZED,),
            provenance=provenance,
        )
    return PostureProjection(
        posture=posture,
        evaluated_posture=posture,
        trust_status=TrustStatus.TRUSTED,
        reason_codes=(BriefReasonCode.POSTURE_FROM_ACCEPTED_FACT,),
        provenance=provenance,
    )


def _decision_projection(fact: CanonicalFact) -> AcceptedDecisionProjection:
    return AcceptedDecisionProjection(
        subject_id=fact.subject_id,
        attribute=fact.attribute,
        accepted_value=fact.value,
        accepted_by_actor_id=fact.accepted_by_actor_id,
        accepted_at=fact.accepted_at,
        source_candidate_fact_id=fact.source_candidate_fact_id,
        provenance=(_fact_provenance(fact),),
    )


def _fact_provenance(fact: CanonicalFact) -> ProjectionProvenance:
    return ProjectionProvenance(
        kind=ProvenanceKind.ACCEPTED_FACT,
        source_id=fact.source_candidate_fact_id,
        evidence_ids=fact.evidence_ids,
    )


def _state_provenance(state: ProjectState) -> ProjectionProvenance:
    source_id = state.applied_event_ids[-1] if state.applied_event_ids else state.project_id
    return ProjectionProvenance(kind=ProvenanceKind.PROJECT_STATE, source_id=source_id)


def _recommendation_provenance(
    action: RecommendedAction,
    state: ProjectState,
) -> tuple[ProjectionProvenance, ...]:
    findings = tuple(
        ProjectionProvenance(
            kind=ProvenanceKind.INVARIANT_RESULT,
            source_id=finding.object_id,
        )
        for finding in action.supporting_findings
    )
    evidence = tuple(
        ProjectionProvenance(
            kind=ProvenanceKind.EVIDENCE,
            source_id=reference.evidence_id,
            evidence_status=reference.status,
        )
        for reference in action.supporting_evidence
    )
    assumptions = tuple(
        ProjectionProvenance(
            kind=ProvenanceKind.ASSUMPTION,
            source_id=assumption.object_id,
        )
        for assumption in action.unresolved_assumptions
    )
    blockers = tuple(
        ProjectionProvenance(
            kind=ProvenanceKind.BLOCKER,
            source_id=blocker.blocker_id,
        )
        for blocker in action.blockers
    )
    return findings + evidence + assumptions + blockers or (_state_provenance(state),)
