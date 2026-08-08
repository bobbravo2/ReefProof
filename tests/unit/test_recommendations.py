"""Deterministic recommended-action domain tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reefproof.recommendations import (
    ActionBlocker,
    ActionPriority,
    ActionType,
    BlockerState,
    Determinacy,
    DomainReference,
    EvidenceReference,
    EvidenceStatus,
    ExpectedStateTransition,
    ReasonCode,
    RecommendedAction,
    explain_recommended_action,
    select_recommended_action,
)


def _action(
    action_id: str,
    reason: ReasonCode,
    *,
    determinacy: Determinacy = Determinacy.DETERMINATE,
    evidence: tuple[EvidenceReference, ...] = (),
    assumptions: tuple[DomainReference, ...] = (),
    blockers: tuple[ActionBlocker, ...] = (),
) -> RecommendedAction:
    return RecommendedAction(
        action_id=action_id,
        action_type=ActionType.RECORD_OBSERVATION,
        affected_objects=(DomainReference(object_type="equipment", object_id="return_pump"),),
        reason_codes=(reason,),
        supporting_findings=(DomainReference(object_type="finding", object_id="RP-FLOW-001"),),
        supporting_evidence=evidence,
        unresolved_assumptions=assumptions,
        blockers=blockers,
        expected_transition=ExpectedStateTransition(
            state_type="assurance_state",
            from_state="UNKNOWN",
            to_state="PASS",
        ),
        determinacy=determinacy,
        human_judgment_required=True,
    )


@pytest.mark.parametrize(
    ("reason", "priority"),
    [
        (ReasonCode.HUMAN_SAFETY, ActionPriority.HUMAN_OR_PROPERTY_SAFETY),
        (ReasonCode.CATASTROPHIC_FAILURE_RISK, ActionPriority.CATASTROPHIC_FAILURE_PREVENTION),
        (ReasonCode.COMMISSIONING_BLOCKED, ActionPriority.COMMISSIONING_BLOCKER),
        (ReasonCode.HIGH_IMPACT_UNKNOWN, ActionPriority.HIGH_IMPACT_UNKNOWN),
        (ReasonCode.DEPENDENCY_PREREQUISITE, ActionPriority.DEPENDENCY_PREREQUISITE),
        (ReasonCode.EVIDENCE_STALE, ActionPriority.EVIDENCE_FRESHNESS),
        (ReasonCode.OPERATIONAL_RELIABILITY, ActionPriority.OPERATIONAL_RELIABILITY),
        (ReasonCode.AESTHETICS, ActionPriority.CONVENIENCE_OR_AESTHETICS),
    ],
)
def test_every_adr_priority_tier_is_derived_from_reason_codes(
    reason: ReasonCode,
    priority: ActionPriority,
) -> None:
    assert _action("check-system", reason).priority is priority


def test_selector_uses_exact_priority_order_independent_of_input_order() -> None:
    actions = tuple(
        _action(f"action-{priority.value}", reason)
        for priority, reason in (
            (ActionPriority.CONVENIENCE_OR_AESTHETICS, ReasonCode.CONVENIENCE),
            (ActionPriority.OPERATIONAL_RELIABILITY, ReasonCode.OPERATIONAL_RELIABILITY),
            (ActionPriority.EVIDENCE_FRESHNESS, ReasonCode.EVIDENCE_MISSING),
            (ActionPriority.DEPENDENCY_PREREQUISITE, ReasonCode.DEPENDENCY_PREREQUISITE),
            (ActionPriority.HIGH_IMPACT_UNKNOWN, ReasonCode.HIGH_IMPACT_UNKNOWN),
            (ActionPriority.COMMISSIONING_BLOCKER, ReasonCode.COMMISSIONING_BLOCKED),
            (
                ActionPriority.CATASTROPHIC_FAILURE_PREVENTION,
                ReasonCode.CATASTROPHIC_FAILURE_RISK,
            ),
            (ActionPriority.HUMAN_OR_PROPERTY_SAFETY, ReasonCode.PROPERTY_SAFETY),
        )
    )

    selected = select_recommended_action(actions)

    assert selected is not None
    assert selected.priority is ActionPriority.HUMAN_OR_PROPERTY_SAFETY
    assert selected.action_id == "action-1"


def test_selector_has_stable_identity_tie_break_and_empty_result() -> None:
    later = _action("z-last", ReasonCode.COMMISSIONING_BLOCKED)
    first = _action("a-first", ReasonCode.COMMISSIONING_BLOCKED)

    assert select_recommended_action((later, first)) == first
    assert select_recommended_action((first, later)) == first
    assert select_recommended_action(()) is None


@pytest.mark.parametrize(
    ("evidence", "assumptions", "blockers"),
    [
        (
            (EvidenceReference(evidence_id="photo-return", status=EvidenceStatus.MISSING),),
            (),
            (),
        ),
        (
            (EvidenceReference(evidence_id="inspection-2026", status=EvidenceStatus.STALE),),
            (),
            (),
        ),
        (
            (),
            (DomainReference(object_type="assumption", object_id="return-path-clear"),),
            (),
        ),
        (
            (),
            (),
            (
                ActionBlocker(
                    blocker_id="verify-power",
                    state=BlockerState.UNKNOWN,
                    reason_code=ReasonCode.DEPENDENCY_PREREQUISITE,
                ),
            ),
        ),
    ],
)
def test_unknown_determinacy_requires_explicit_unknown_basis(
    evidence: tuple[EvidenceReference, ...],
    assumptions: tuple[DomainReference, ...],
    blockers: tuple[ActionBlocker, ...],
) -> None:
    action = _action(
        "resolve-unknown",
        ReasonCode.HIGH_IMPACT_UNKNOWN,
        determinacy=Determinacy.UNKNOWN,
        evidence=evidence,
        assumptions=assumptions,
        blockers=blockers,
    )

    assert action.determinacy is Determinacy.UNKNOWN


def test_absence_of_evidence_is_not_accepted_as_unknown_evidence() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN determinacy requires"):
        _action(
            "unsupported-unknown",
            ReasonCode.HIGH_IMPACT_UNKNOWN,
            determinacy=Determinacy.UNKNOWN,
        )


def test_determinate_action_rejects_missing_evidence() -> None:
    with pytest.raises(ValidationError, match="determinate action"):
        _action(
            "false-certainty",
            ReasonCode.EVIDENCE_MISSING,
            evidence=(
                EvidenceReference(evidence_id="required-test", status=EvidenceStatus.MISSING),
            ),
        )


def test_template_narration_is_reproducible_and_cannot_alter_ranking() -> None:
    safety = _action("inspect-leak", ReasonCode.HUMAN_SAFETY)
    aesthetics = _action("arrange-cables", ReasonCode.AESTHETICS)

    explanation = explain_recommended_action(aesthetics)
    selected_before = select_recommended_action((aesthetics, safety))
    selected_after = select_recommended_action((aesthetics, safety))

    assert explanation == (
        "arrange-cables is recommended because it improves convenience or aesthetics. "
        "It affects equipment:return_pump and has 1 supporting reference(s). "
        "Human judgment is required."
    )
    assert selected_before == safety
    assert selected_after == safety


def test_action_is_immutable_and_rejects_untyped_extra_narration() -> None:
    action = _action("inspect-leak", ReasonCode.HUMAN_SAFETY)

    with pytest.raises(ValidationError, match="frozen"):
        action.action_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        RecommendedAction.model_validate({**action.model_dump(), "llm_priority": 0})
