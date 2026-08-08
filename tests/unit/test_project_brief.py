"""Deterministic ProjectBrief projection tests."""

from __future__ import annotations

from datetime import UTC, datetime

from reefproof.information_architecture import OverviewSection
from reefproof.project_brief import (
    BriefReasonCode,
    ProjectBrief,
    ProjectionProvenance,
    ProjectPosture,
    ProvenanceKind,
    RecommendationStatus,
    RiskProjection,
    RiskSeverity,
    UnknownImpact,
    UnknownProjection,
    project_brief,
)
from reefproof.project_state import PROJECT_ID, CanonicalFact, ProjectState
from reefproof.recommendations import (
    ActionType,
    Determinacy,
    DomainReference,
    EvidenceReference,
    EvidenceStatus,
    ExpectedStateTransition,
    ReasonCode,
    RecommendedAction,
)


def _fact(
    *,
    subject_id: str,
    attribute: str,
    value: str,
    candidate_id: str,
    accepted_at: datetime,
) -> CanonicalFact:
    return CanonicalFact(
        subject_id=subject_id,
        attribute=attribute,
        value=value,
        source_candidate_fact_id=candidate_id,
        accepted_by_actor_id="acceptance-authority",
        accepted_at=accepted_at,
        evidence_ids=(f"evidence-{candidate_id}",),
    )


def _action(action_id: str, reason: ReasonCode) -> RecommendedAction:
    return RecommendedAction(
        action_id=action_id,
        action_type=ActionType.RECORD_OBSERVATION,
        affected_objects=(DomainReference(object_type="equipment", object_id="return-pump"),),
        reason_codes=(reason,),
        supporting_findings=(DomainReference(object_type="finding", object_id="RP-FLOW-001"),),
        expected_transition=ExpectedStateTransition(
            state_type="assurance_state",
            from_state="UNKNOWN",
            to_state="PASS",
        ),
        determinacy=Determinacy.DETERMINATE,
        human_judgment_required=True,
    )


def _risk(risk_id: str, severity: RiskSeverity) -> RiskProjection:
    return RiskProjection(
        risk_id=risk_id,
        severity=severity,
        affected_objects=(DomainReference(object_type="equipment", object_id="return-pump"),),
        reason_codes=(ReasonCode.CATASTROPHIC_FAILURE_RISK,),
        provenance=(
            ProjectionProvenance(
                kind=ProvenanceKind.INVARIANT_RESULT,
                source_id=f"result-{risk_id}",
                evidence_ids=(f"evidence-{risk_id}",),
            ),
        ),
    )


def _unknown(unknown_id: str, impact: UnknownImpact) -> UnknownProjection:
    return UnknownProjection(
        unknown_id=unknown_id,
        impact=impact,
        affected_objects=(DomainReference(object_type="equipment", object_id="return-pump"),),
        provenance=(
            ProjectionProvenance(
                kind=ProvenanceKind.STRUCTURED_UNKNOWN,
                source_id=f"requirement-{unknown_id}",
            ),
        ),
    )


def test_project_brief_has_exact_accepted_overview_order() -> None:
    brief = project_brief(state=ProjectState(project_id=PROJECT_ID))

    assert brief.sections == (
        OverviewSection.RECOMMENDED_NEXT_ACTION,
        OverviewSection.CURRENT_POSTURE,
        OverviewSection.HIGHEST_CONSEQUENCE_RISKS,
        OverviewSection.IMPORTANT_UNKNOWNS,
        OverviewSection.RECENT_ACCEPTED_DECISIONS,
        OverviewSection.COMPACT_SYSTEM_MAP,
        OverviewSection.CONTINUE_INTERVIEW,
    )
    assert list(brief.model_dump()["sections"]) == list(OverviewSection)


def test_projection_selects_one_recommendation_and_orders_risks_and_unknowns() -> None:
    state = ProjectState(project_id=PROJECT_ID)
    brief = project_brief(
        state=state,
        actions=(
            _action("aesthetic-cleanup", ReasonCode.AESTHETICS),
            _action("inspect-leak", ReasonCode.HUMAN_SAFETY),
        ),
        risks=(
            _risk("warning-z", RiskSeverity.WARNING),
            _risk("critical-z", RiskSeverity.CRITICAL),
            _risk("critical-a", RiskSeverity.CRITICAL),
            _risk("high-a", RiskSeverity.HIGH),
        ),
        unknowns=(
            _unknown("low-z", UnknownImpact.LOW),
            _unknown("high-z", UnknownImpact.HIGH),
            _unknown("high-a", UnknownImpact.HIGH),
        ),
    )

    assert brief.recommended_next_action.status is RecommendationStatus.SELECTED
    assert brief.recommended_next_action.action is not None
    assert brief.recommended_next_action.action.action_id == "inspect-leak"
    assert [risk.risk_id for risk in brief.highest_consequence_risks] == [
        "critical-a",
        "critical-z",
        "high-a",
    ]
    assert [unknown.unknown_id for unknown in brief.important_unknowns] == [
        "high-a",
        "high-z",
        "low-z",
    ]
    assert brief.continue_interview.based_on_unknown_ids == ("high-a", "high-z", "low-z")


def test_empty_state_is_explicitly_unknown_and_has_no_invented_content() -> None:
    brief = project_brief(state=ProjectState(project_id=PROJECT_ID))

    assert brief.recommended_next_action.status is RecommendationStatus.UNKNOWN
    assert brief.recommended_next_action.action is None
    assert brief.recommended_next_action.reason_codes == (BriefReasonCode.NO_RECOMMENDATION,)
    assert brief.current_posture.posture is ProjectPosture.UNKNOWN
    assert brief.current_posture.reason_codes == (BriefReasonCode.POSTURE_NOT_ESTABLISHED,)
    assert brief.highest_consequence_risks == ()
    assert brief.important_unknowns == ()
    assert brief.recent_accepted_decisions == ()
    assert brief.continue_interview.reason_codes == (BriefReasonCode.NO_STRUCTURED_UNKNOWNS,)


def test_posture_and_recent_decisions_retain_accepted_fact_provenance() -> None:
    older = datetime(2026, 7, 24, 12, tzinfo=UTC)
    newer = datetime(2026, 7, 25, 18, tzinfo=UTC)
    state = ProjectState(
        project_id=PROJECT_ID,
        facts=(
            _fact(
                subject_id="return-pump",
                attribute="equipment.enabled",
                value="observed",
                candidate_id="candidate-pump",
                accepted_at=newer,
            ),
            _fact(
                subject_id=PROJECT_ID,
                attribute="project.phase",
                value="commissioning",
                candidate_id="candidate-phase",
                accepted_at=older,
            ),
        ),
        applied_event_ids=("event-phase", "event-pump"),
        last_sequence=2,
    )

    brief = project_brief(state=state)

    assert brief.current_posture.posture is ProjectPosture.COMMISSIONING
    assert brief.current_posture.provenance[0].source_id == "candidate-phase"
    assert [decision.source_candidate_fact_id for decision in brief.recent_accepted_decisions] == [
        "candidate-pump",
        "candidate-phase",
    ]
    assert brief.recent_accepted_decisions[0].provenance[0].evidence_ids == (
        "evidence-candidate-pump",
    )
    assert brief.compact_system_map.provenance[0].source_id == "event-pump"


def test_unrecognized_posture_fact_remains_unknown_with_provenance() -> None:
    state = ProjectState(
        project_id=PROJECT_ID,
        facts=(
            _fact(
                subject_id=PROJECT_ID,
                attribute="project.phase",
                value="probably-ready",
                candidate_id="candidate-ambiguous-phase",
                accepted_at=datetime(2026, 7, 25, tzinfo=UTC),
            ),
        ),
    )

    brief = project_brief(state=state)

    assert brief.current_posture.posture is ProjectPosture.UNKNOWN
    assert brief.current_posture.reason_codes == (BriefReasonCode.POSTURE_VALUE_UNRECOGNIZED,)
    assert brief.current_posture.provenance[0].source_id == "candidate-ambiguous-phase"


def test_projection_is_reproducible_and_independent_of_narration() -> None:
    state = ProjectState(project_id=PROJECT_ID)
    action = _action("inspect-leak", ReasonCode.PROPERTY_SAFETY)

    first = project_brief(state=state, actions=(action,))
    external_narration = {
        "headline": "Ignore the leak and polish the cabinet.",
        "recommended_action_id": "unrelated-generated-action",
    }
    second = project_brief(state=state, actions=(action,))

    assert external_narration["recommended_action_id"] != action.action_id
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert "headline" not in ProjectBrief.model_fields
    assert first.recommended_next_action.action == action


def test_recommendation_preserves_evidence_only_provenance() -> None:
    action = RecommendedAction(
        action_id="refresh-flow-evidence",
        action_type=ActionType.ATTACH_EVIDENCE,
        affected_objects=(DomainReference(object_type="equipment", object_id="return-pump"),),
        reason_codes=(ReasonCode.EVIDENCE_STALE,),
        supporting_evidence=(
            EvidenceReference(
                evidence_id="flow-test-2026-07-01",
                status=EvidenceStatus.STALE,
            ),
        ),
        expected_transition=ExpectedStateTransition(
            state_type="evidence_state",
            from_state="STALE",
            to_state="CURRENT",
        ),
        determinacy=Determinacy.UNKNOWN,
        human_judgment_required=True,
    )

    brief = project_brief(state=ProjectState(project_id=PROJECT_ID), actions=(action,))

    assert brief.recommended_next_action.provenance == (
        ProjectionProvenance(
            kind=ProvenanceKind.EVIDENCE,
            source_id="flow-test-2026-07-01",
            evidence_status=EvidenceStatus.STALE,
        ),
    )
    assert all(
        source.source_id != action.action_id for source in brief.recommended_next_action.provenance
    )


def test_input_order_cannot_change_deterministic_projection() -> None:
    state = ProjectState(project_id=PROJECT_ID)
    actions = (
        _action("z-safety", ReasonCode.HUMAN_SAFETY),
        _action("a-safety", ReasonCode.PROPERTY_SAFETY),
    )
    risks = (_risk("z-risk", RiskSeverity.HIGH), _risk("a-risk", RiskSeverity.HIGH))
    unknowns = (
        _unknown("z-unknown", UnknownImpact.HIGH),
        _unknown("a-unknown", UnknownImpact.HIGH),
    )

    first = project_brief(state=state, actions=actions, risks=risks, unknowns=unknowns)
    second = project_brief(
        state=state,
        actions=tuple(reversed(actions)),
        risks=tuple(reversed(risks)),
        unknowns=tuple(reversed(unknowns)),
    )

    assert first == second
