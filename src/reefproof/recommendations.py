"""Deterministic recommended-action contracts and selection.

This module deliberately has no dependency on presentation, persistence, device
transport, or an LLM.  A recommendation's priority is derived from its typed
reason codes, so explanatory language cannot silently change ranking.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionPriority(IntEnum):
    """ADR 0003 ranking order; lower values are more important."""

    HUMAN_OR_PROPERTY_SAFETY = 1
    CATASTROPHIC_FAILURE_PREVENTION = 2
    COMMISSIONING_BLOCKER = 3
    HIGH_IMPACT_UNKNOWN = 4
    DEPENDENCY_PREREQUISITE = 5
    EVIDENCE_FRESHNESS = 6
    OPERATIONAL_RELIABILITY = 7
    CONVENIENCE_OR_AESTHETICS = 8


class ReasonCode(StrEnum):
    HUMAN_SAFETY = "human_safety"
    PROPERTY_SAFETY = "property_safety"
    CATASTROPHIC_FAILURE_RISK = "catastrophic_failure_risk"
    COMMISSIONING_BLOCKED = "commissioning_blocked"
    HIGH_IMPACT_UNKNOWN = "high_impact_unknown"
    DEPENDENCY_PREREQUISITE = "dependency_prerequisite"
    EVIDENCE_MISSING = "evidence_missing"
    EVIDENCE_STALE = "evidence_stale"
    OPERATIONAL_RELIABILITY = "operational_reliability"
    CONVENIENCE = "convenience"
    AESTHETICS = "aesthetics"


_REASON_PRIORITY: dict[ReasonCode, ActionPriority] = {
    ReasonCode.HUMAN_SAFETY: ActionPriority.HUMAN_OR_PROPERTY_SAFETY,
    ReasonCode.PROPERTY_SAFETY: ActionPriority.HUMAN_OR_PROPERTY_SAFETY,
    ReasonCode.CATASTROPHIC_FAILURE_RISK: ActionPriority.CATASTROPHIC_FAILURE_PREVENTION,
    ReasonCode.COMMISSIONING_BLOCKED: ActionPriority.COMMISSIONING_BLOCKER,
    ReasonCode.HIGH_IMPACT_UNKNOWN: ActionPriority.HIGH_IMPACT_UNKNOWN,
    ReasonCode.DEPENDENCY_PREREQUISITE: ActionPriority.DEPENDENCY_PREREQUISITE,
    ReasonCode.EVIDENCE_MISSING: ActionPriority.EVIDENCE_FRESHNESS,
    ReasonCode.EVIDENCE_STALE: ActionPriority.EVIDENCE_FRESHNESS,
    ReasonCode.OPERATIONAL_RELIABILITY: ActionPriority.OPERATIONAL_RELIABILITY,
    ReasonCode.CONVENIENCE: ActionPriority.CONVENIENCE_OR_AESTHETICS,
    ReasonCode.AESTHETICS: ActionPriority.CONVENIENCE_OR_AESTHETICS,
}


class ActionType(StrEnum):
    RESOLVE_UNKNOWN = "resolve_unknown"
    RECORD_OBSERVATION = "record_observation"
    ATTACH_EVIDENCE = "attach_evidence"
    REVIEW_CANDIDATE_FACTS = "review_candidate_facts"
    REVIEW_DEPENDENCY = "review_dependency"
    CHALLENGE_FINDING = "challenge_finding"
    OPERATOR_DECISION = "operator_decision"


class Determinacy(StrEnum):
    DETERMINATE = "DETERMINATE"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    STALE = "stale"


class BlockerState(StrEnum):
    UNMET = "unmet"
    UNKNOWN = "unknown"


class DomainReference(BaseModel):
    """Stable reference to an affected canonical domain object."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_type: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    object_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")


class EvidenceReference(BaseModel):
    """Evidence identity plus adequacy; missing is not silently treated as false."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    evidence_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    status: EvidenceStatus


class ActionBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    blocker_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    state: BlockerState
    reason_code: ReasonCode
    affected_object: DomainReference | None = None


class ExpectedStateTransition(BaseModel):
    """The state change expected after a human completes the action."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    state_type: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    from_state: str = Field(min_length=1)
    to_state: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_actual_transition(self) -> Self:
        if self.from_state == self.to_state:
            raise ValueError("expected transition must change state")
        return self


class RecommendedAction(BaseModel):
    """Immutable canonical input to deterministic action selection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    action_type: ActionType
    affected_objects: tuple[DomainReference, ...] = Field(min_length=1)
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)
    supporting_findings: tuple[DomainReference, ...] = ()
    supporting_evidence: tuple[EvidenceReference, ...] = ()
    unresolved_assumptions: tuple[DomainReference, ...] = ()
    blockers: tuple[ActionBlocker, ...] = ()
    expected_transition: ExpectedStateTransition
    determinacy: Determinacy
    human_judgment_required: bool

    @property
    def priority(self) -> ActionPriority:
        """Return the highest priority implied by this action's reasons."""

        return min(_REASON_PRIORITY[reason] for reason in self.reason_codes)

    @model_validator(mode="after")
    def preserve_unknown_semantics(self) -> Self:
        evidence_is_inadequate = any(
            evidence.status is not EvidenceStatus.AVAILABLE for evidence in self.supporting_evidence
        )
        blocker_is_unknown = any(blocker.state is BlockerState.UNKNOWN for blocker in self.blockers)
        has_unknown_basis = (
            evidence_is_inadequate or blocker_is_unknown or bool(self.unresolved_assumptions)
        )
        if self.determinacy is Determinacy.UNKNOWN and not has_unknown_basis:
            raise ValueError(
                "UNKNOWN determinacy requires missing/stale evidence, an unknown blocker, "
                "or an unresolved assumption"
            )
        if self.determinacy is Determinacy.DETERMINATE and has_unknown_basis:
            raise ValueError("a determinate action cannot contain an unresolved unknown")
        return self


def select_recommended_action(
    actions: tuple[RecommendedAction, ...],
) -> RecommendedAction | None:
    """Select one action by ADR priority and stable action identity.

    The lexical identifier tie-break is intentionally independent of input
    ordering, generated prose, and model availability.
    """

    return min(actions, key=lambda action: (action.priority, action.action_id), default=None)


_PRIORITY_EXPLANATIONS: dict[ActionPriority, str] = {
    ActionPriority.HUMAN_OR_PROPERTY_SAFETY: "protects human or property safety",
    ActionPriority.CATASTROPHIC_FAILURE_PREVENTION: "reduces catastrophic system-failure risk",
    ActionPriority.COMMISSIONING_BLOCKER: "removes a commissioning blocker",
    ActionPriority.HIGH_IMPACT_UNKNOWN: "resolves a high-impact unknown",
    ActionPriority.DEPENDENCY_PREREQUISITE: "completes a dependency prerequisite",
    ActionPriority.EVIDENCE_FRESHNESS: "restores missing or stale evidence",
    ActionPriority.OPERATIONAL_RELIABILITY: "improves operational reliability",
    ActionPriority.CONVENIENCE_OR_AESTHETICS: "improves convenience or aesthetics",
}


def explain_recommended_action(action: RecommendedAction) -> str:
    """Render a reproducible, no-LLM explanation from structured fields."""

    affected = ", ".join(
        f"{reference.object_type}:{reference.object_id}"
        for reference in sorted(
            action.affected_objects,
            key=lambda reference: (reference.object_type, reference.object_id),
        )
    )
    basis_count = len(action.supporting_findings) + len(action.supporting_evidence)
    judgment = " Human judgment is required." if action.human_judgment_required else ""
    return (
        f"{action.action_id} is recommended because it "
        f"{_PRIORITY_EXPLANATIONS[action.priority]}. "
        f"It affects {affected} and has {basis_count} supporting reference(s)."
        f"{judgment}"
    )
