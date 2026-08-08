"""Deterministic canonical-state and interview audit tests."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from reefproof.project_state import (
    AcceptedFactRecord,
    Actor,
    ActorRole,
    CandidateDecision,
    CandidateDecisionKind,
    CandidateFact,
    CandidateValidation,
    DomainEvent,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Project,
    decide_candidate,
    replay_project,
)

NOW = datetime(2026, 7, 25, 18, 0, tzinfo=UTC)
PROJECT_ID = "primary-reef-system"


def project() -> Project:
    return Project(
        project_id=PROJECT_ID,
        acceptance_authority_principal_id="acceptance-authority",
        created_at=NOW,
    )


def authority() -> Actor:
    return Actor(
        actor_id="acceptance-authority",
        display_name="Acceptance authority",
        role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
    )


def candidate() -> CandidateFact:
    return CandidateFact(
        candidate_fact_id="candidate-return-pump-model",
        project_id=PROJECT_ID,
        subject_id="return_pump",
        attribute="equipment.model",
        proposed_value="Varios-8",
        proposed_by_actor_id="reefproof-agent",
        proposed_at=NOW,
        source_answer_id="answer-return-pump-model",
        evidence_ids=("evidence-interview-1",),
    )


def validation(*, valid: bool = True) -> CandidateValidation:
    return CandidateValidation(
        candidate_fact_id="candidate-return-pump-model",
        schema_valid=valid,
        domain_valid=valid,
        reason_codes=() if valid else ("VALUE_NOT_SUPPORTED",),
        validated_at=NOW,
    )


def test_interview_preserves_attributable_candidate_provenance() -> None:
    question = InterviewQuestion(
        question_id="question-return-pump-model",
        prompt="Which return pump model is installed?",
        reason_codes=("MISSING_EQUIPMENT_MODEL",),
        affected_subject_ids=("return_pump",),
    )
    answer = InterviewAnswer(
        answer_id="answer-return-pump-model",
        question_id=question.question_id,
        answered_by_actor_id="acceptance-authority",
        answered_at=NOW,
        source_statement="The return pump is a Varios-8.",
        evidence_ids=("evidence-interview-1",),
    )
    session = InterviewSession(
        session_id="session-commissioning-1",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=NOW,
        purpose="Resolve commissioning unknowns",
        scope_subject_ids=("return_pump",),
        questions=(question,),
        answers=(answer,),
        candidate_facts=(candidate(),),
        transcript_evidence_id="evidence-interview-1",
    )

    assert session.initiated_by_actor_id == "acceptance-authority"
    assert session.candidate_facts[0].proposed_by_actor_id == "reefproof-agent"
    assert session.candidate_facts[0].source_answer_id == answer.answer_id
    assert session.answers[0].source_statement == "The return pump is a Varios-8."


def test_candidate_and_rejection_do_not_change_canonical_state() -> None:
    empty = replay_project(project(), ())
    rejection, event = decide_candidate(
        project=project(),
        candidate=candidate(),
        validation=validation(),
        deciding_actor=authority(),
        decision=CandidateDecisionKind.REJECTED,
        decision_id="decision-reject-return-pump",
        decided_at=NOW,
        rationale="The label photograph does not support this model.",
    )
    question = InterviewQuestion(
        question_id="question-return-pump-model",
        prompt="Which model is installed?",
        reason_codes=("MISSING_EQUIPMENT_MODEL",),
    )
    answer = InterviewAnswer(
        answer_id="answer-return-pump-model",
        question_id=question.question_id,
        answered_by_actor_id="acceptance-authority",
        answered_at=NOW,
        source_statement="It may be a Varios-8.",
    )
    session = InterviewSession(
        session_id="session-review-1",
        project_id=PROJECT_ID,
        initiated_by_actor_id="acceptance-authority",
        initiated_at=NOW,
        purpose="Review proposed facts",
        scope_subject_ids=("return_pump",),
        questions=(question,),
        answers=(answer,),
        candidate_facts=(candidate(),),
        decisions=(rejection,),
    )

    assert event is None
    assert empty.facts == ()
    assert session.decisions[0].decision is CandidateDecisionKind.REJECTED
    assert session.decisions[0].resulting_domain_event_id is None


def test_only_acceptance_authority_acceptance_produces_an_event_and_canonical_fact() -> None:
    agent = Actor(
        actor_id="reefproof-agent",
        display_name="ReefProof Agent",
        role=ActorRole.AGENT,
    )
    with pytest.raises(PermissionError, match="only the human acceptance authority"):
        decide_candidate(
            project=project(),
            candidate=candidate(),
            validation=validation(),
            deciding_actor=agent,
            decision=CandidateDecisionKind.ACCEPTED,
            decision_id="decision-agent-accept",
            decided_at=NOW,
            rationale="Looks plausible.",
            next_event_id="event-agent-accept",
            next_sequence=1,
        )

    # Even a directly constructed event cannot bypass replay authority.
    forged_event = DomainEvent(
        event_id="event-forged",
        project_id=project().project_id,
        sequence=1,
        occurred_at=NOW,
        actor_id=agent.actor_id,
        candidate_fact_id=candidate().candidate_fact_id,
        subject_id=candidate().subject_id,
        attribute=candidate().attribute,
        value=candidate().proposed_value,
    )
    with pytest.raises(ValidationError, match="decision and event identities"):
        AcceptedFactRecord(
            candidate=candidate(),
            decision=CandidateDecision(
                decision_id="decision-forged",
                candidate_fact_id=candidate().candidate_fact_id,
                decision=CandidateDecisionKind.ACCEPTED,
                decided_by_actor_id="acceptance-authority",
                decided_at=NOW,
                validation=validation(),
                rationale="Forged.",
                resulting_domain_event_id="event-other",
            ),
            event=forged_event,
        )

    decision, event = decide_candidate(
        project=project(),
        candidate=candidate(),
        validation=validation(),
        deciding_actor=authority(),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id="decision-authority-accept",
        decided_at=NOW,
        rationale="Confirmed from the equipment label.",
        next_event_id="event-return-pump-model",
        next_sequence=1,
    )
    assert event is not None
    record = AcceptedFactRecord(candidate=candidate(), decision=decision, event=event)
    state = replay_project(project(), (record,))

    fact = state.fact("return_pump", "equipment.model")
    assert decision.resulting_domain_event_id == event.event_id
    assert fact is not None
    assert fact.value == "Varios-8"
    assert fact.accepted_by_actor_id == "acceptance-authority"
    assert fact.source_candidate_fact_id == candidate().candidate_fact_id
    assert fact.evidence_ids == ("evidence-interview-1",)


def test_invalid_candidate_cannot_be_accepted() -> None:
    with pytest.raises(ValueError, match="invalid candidate"):
        decide_candidate(
            project=project(),
            candidate=candidate(),
            validation=validation(valid=False),
            deciding_actor=authority(),
            decision=CandidateDecisionKind.ACCEPTED,
            decision_id="decision-invalid-accept",
            decided_at=NOW,
            rationale="Accept anyway.",
            next_event_id="event-invalid",
            next_sequence=1,
        )


def test_event_replay_is_deterministic_and_rejects_incomplete_history() -> None:
    first_decision, first_event = decide_candidate(
        project=project(),
        candidate=candidate(),
        validation=validation(),
        deciding_actor=authority(),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id="decision-first-replay",
        decided_at=NOW,
        rationale="Confirmed.",
        next_event_id="event-first-replay",
        next_sequence=1,
    )
    assert first_event is not None
    record = AcceptedFactRecord(
        candidate=candidate(),
        decision=first_decision,
        event=first_event,
    )
    assert replay_project(project(), (record,)) == replay_project(project(), (record,))
    with pytest.raises(ValueError, match="contiguous sequence"):
        replay_project(
            project(),
            (record.model_copy(update={"event": first_event.model_copy(update={"sequence": 2})}),),
        )


@pytest.mark.parametrize(
    ("part", "updates", "message"),
    [
        ("decision", {"resulting_domain_event_id": "event-other"}, "decision and event"),
        ("event", {"candidate_fact_id": "candidate-other"}, "event and candidate"),
        ("event", {"actor_id": "reefproof-agent"}, "event actor"),
        ("event", {"value": "Different pump"}, "event payload"),
        ("event", {"evidence_ids": ("evidence-other",)}, "event payload"),
    ],
)
def test_replay_authority_chain_rejects_tampering(
    part: str,
    updates: dict[str, object],
    message: str,
) -> None:
    decision, event = decide_candidate(
        project=project(),
        candidate=candidate(),
        validation=validation(),
        deciding_actor=authority(),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id="decision-authority-chain",
        decided_at=NOW,
        rationale="Confirmed.",
        next_event_id="event-authority-chain",
        next_sequence=1,
    )
    assert event is not None
    payload = AcceptedFactRecord(
        candidate=candidate(),
        decision=decision,
        event=event,
    ).model_dump()
    nested = payload[part]
    assert isinstance(nested, dict)
    nested.update(updates)

    with pytest.raises(ValidationError, match=message):
        AcceptedFactRecord.model_validate(payload)


def test_replay_rejects_event_without_candidate_and_accepted_decision() -> None:
    event = DomainEvent(
        event_id="event-unreviewed",
        project_id=PROJECT_ID,
        sequence=1,
        occurred_at=NOW,
        actor_id="acceptance-authority",
        candidate_fact_id="candidate-unreviewed",
        subject_id="return_pump",
        attribute="equipment.model",
        value="Unreviewed",
    )

    with pytest.raises(ValidationError, match="Field required"):
        AcceptedFactRecord.model_validate({"event": event})


def test_models_reject_missing_provenance_and_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        CandidateFact(
            candidate_fact_id="candidate-naive",
            project_id=PROJECT_ID,
            subject_id="return_pump",
            attribute="equipment.model",
            proposed_value="Unknown",
            proposed_by_actor_id="reefproof-agent",
            proposed_at=datetime(2026, 7, 25),
        )

    with pytest.raises(ValidationError, match="source-answer provenance"):
        InterviewSession(
            session_id="session-bad-provenance",
            project_id=PROJECT_ID,
            initiated_by_actor_id="acceptance-authority",
            initiated_at=NOW,
            purpose="Bad provenance",
            scope_subject_ids=("return_pump",),
            candidate_facts=(candidate(),),
        )


def test_no_llm_is_needed_to_accept_and_replay_project_truth() -> None:
    decision, event = decide_candidate(
        project=project(),
        candidate=candidate(),
        validation=validation(),
        deciding_actor=authority(),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id="decision-offline",
        decided_at=NOW,
        rationale="the acceptance authority directly entered and confirmed this fact.",
        next_event_id="event-offline",
        next_sequence=1,
    )

    assert decision.decision is CandidateDecisionKind.ACCEPTED
    assert event is not None
    record = AcceptedFactRecord(candidate=candidate(), decision=decision, event=event)
    assert replay_project(project(), (record,)).fact("return_pump", "equipment.model") is not None
