"""Typed, deterministic project-state and interview audit models.

This module has no persistence, web, device, or LLM dependency. Candidate facts
remain non-canonical until the configured human authority accepts a valid
candidate and an append-only event is replayed into project state.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = str
FactValue = str | int | float | bool
PROJECT_ID = "primary-reef-system"
PROJECT_NAME = "Primary Reef System"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ActorRole(StrEnum):
    HUMAN_ACCEPTANCE_AUTHORITY = "human_acceptance_authority"
    AGENT = "agent"
    PARSER = "parser"


class Actor(FrozenModel):
    actor_id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str = Field(min_length=1)
    role: ActorRole


class Project(FrozenModel):
    project_id: Identifier = PROJECT_ID
    name: str = Field(default=PROJECT_NAME, min_length=1)
    acceptance_authority_principal_id: Identifier
    created_at: datetime

    @model_validator(mode="after")
    def require_absolute_time(self) -> Self:
        _require_absolute(self.created_at, "created_at")
        return self


class InterviewQuestion(FrozenModel):
    question_id: Identifier = Field(pattern=r"^question-[a-z0-9_-]+$")
    prompt: str = Field(min_length=1)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    affected_subject_ids: tuple[Identifier, ...] = ()


class InterviewAnswer(FrozenModel):
    answer_id: Identifier = Field(pattern=r"^answer-[a-z0-9_-]+$")
    question_id: Identifier
    answered_by_actor_id: Identifier
    answered_at: datetime
    source_statement: str = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_absolute_time(self) -> Self:
        _require_absolute(self.answered_at, "answered_at")
        return self


class CandidateFact(FrozenModel):
    candidate_fact_id: Identifier = Field(pattern=r"^candidate-[a-z0-9_-]+$")
    project_id: Identifier
    subject_id: Identifier
    attribute: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    proposed_value: FactValue
    proposed_by_actor_id: Identifier
    proposed_at: datetime
    source_answer_id: Identifier | None = None
    evidence_ids: tuple[Identifier, ...] = ()
    epistemic_state: Literal["candidate"] = "candidate"

    @model_validator(mode="after")
    def require_absolute_time(self) -> Self:
        _require_absolute(self.proposed_at, "proposed_at")
        _require_finite_value(self.proposed_value)
        return self


class CandidateValidation(FrozenModel):
    candidate_fact_id: Identifier
    schema_valid: bool
    domain_valid: bool
    reason_codes: tuple[str, ...]
    validated_at: datetime

    @property
    def is_valid(self) -> bool:
        return self.schema_valid and self.domain_valid

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        _require_absolute(self.validated_at, "validated_at")
        if self.is_valid and self.reason_codes:
            raise ValueError("valid candidate validation cannot contain failure reason codes")
        if not self.is_valid and not self.reason_codes:
            raise ValueError("invalid candidate validation requires reason codes")
        return self


class CandidateDecisionKind(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class CandidateDecision(FrozenModel):
    decision_id: Identifier = Field(pattern=r"^decision-[a-z0-9_-]+$")
    candidate_fact_id: Identifier
    decision: CandidateDecisionKind
    decided_by_actor_id: Identifier
    decided_by_role: Literal["human_acceptance_authority"] = "human_acceptance_authority"
    decided_at: datetime
    validation: CandidateValidation
    rationale: str = Field(min_length=1)
    resulting_domain_event_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        _require_absolute(self.decided_at, "decided_at")
        if self.validation.candidate_fact_id != self.candidate_fact_id:
            raise ValueError("decision validation must describe the same candidate")
        if self.decision is CandidateDecisionKind.ACCEPTED:
            if not self.validation.is_valid:
                raise ValueError("an invalid candidate cannot be accepted")
            if self.resulting_domain_event_id is None:
                raise ValueError("acceptance requires a resulting domain event")
        elif self.resulting_domain_event_id is not None:
            raise ValueError("rejection cannot produce a domain event")
        return self


class CanonicalFact(FrozenModel):
    subject_id: Identifier
    attribute: str
    value: FactValue
    source_candidate_fact_id: Identifier
    accepted_by_actor_id: Identifier
    accepted_at: datetime
    evidence_ids: tuple[Identifier, ...]
    epistemic_state: Literal["fact"] = "fact"

    @model_validator(mode="after")
    def require_absolute_time(self) -> Self:
        _require_absolute(self.accepted_at, "accepted_at")
        _require_finite_value(self.value)
        return self


class DomainEvent(FrozenModel):
    event_id: Identifier = Field(pattern=r"^event-[a-z0-9_-]+$")
    project_id: Identifier
    sequence: int = Field(gt=0)
    event_type: Literal["candidate_fact_accepted"] = "candidate_fact_accepted"
    occurred_at: datetime
    actor_id: Identifier
    candidate_fact_id: Identifier
    subject_id: Identifier
    attribute: str
    value: FactValue
    evidence_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def require_absolute_time(self) -> Self:
        _require_absolute(self.occurred_at, "occurred_at")
        _require_finite_value(self.value)
        return self


class AcceptedFactRecord(FrozenModel):
    """Complete immutable authority chain required for canonical replay."""

    candidate: CandidateFact
    decision: CandidateDecision
    event: DomainEvent

    @model_validator(mode="after")
    def validate_authority_chain(self) -> Self:
        if self.decision.decision is not CandidateDecisionKind.ACCEPTED:
            raise ValueError("canonical replay requires an accepted decision")
        if not self.decision.validation.is_valid:
            raise ValueError("canonical replay requires valid candidate validation")
        if self.decision.candidate_fact_id != self.candidate.candidate_fact_id:
            raise ValueError("decision and candidate identities do not match")
        if self.decision.resulting_domain_event_id != self.event.event_id:
            raise ValueError("decision and event identities do not match")
        if self.event.candidate_fact_id != self.candidate.candidate_fact_id:
            raise ValueError("event and candidate identities do not match")
        if self.event.project_id != self.candidate.project_id:
            raise ValueError("event and candidate projects do not match")
        if self.event.actor_id != self.decision.decided_by_actor_id:
            raise ValueError("event actor does not match the deciding user")
        if self.event.occurred_at != self.decision.decided_at:
            raise ValueError("event time does not match the acceptance time")
        if (
            self.event.subject_id != self.candidate.subject_id
            or self.event.attribute != self.candidate.attribute
            or self.event.value != self.candidate.proposed_value
            or self.event.evidence_ids != self.candidate.evidence_ids
        ):
            raise ValueError("event payload does not match the accepted candidate")
        return self


class InterviewSession(FrozenModel):
    session_id: Identifier = Field(pattern=r"^session-[a-z0-9_-]+$")
    project_id: Identifier
    initiated_by_actor_id: Identifier
    initiated_at: datetime
    purpose: str = Field(min_length=1)
    scope_subject_ids: tuple[Identifier, ...]
    questions: tuple[InterviewQuestion, ...] = ()
    answers: tuple[InterviewAnswer, ...] = ()
    candidate_facts: tuple[CandidateFact, ...] = ()
    decisions: tuple[CandidateDecision, ...] = ()
    transcript_evidence_id: Identifier | None = None
    attachment_evidence_ids: tuple[Identifier, ...] = ()
    closed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_audit_references(self) -> Self:
        _require_absolute(self.initiated_at, "initiated_at")
        if self.closed_at is not None:
            _require_absolute(self.closed_at, "closed_at")
            if self.closed_at < self.initiated_at:
                raise ValueError("closed_at cannot precede initiated_at")
        question_ids = _unique_ids(self.questions, "question_id", "question")
        answer_ids = _unique_ids(self.answers, "answer_id", "answer")
        candidate_ids = _unique_ids(self.candidate_facts, "candidate_fact_id", "candidate")
        _unique_ids(self.decisions, "decision_id", "decision")
        if any(answer.question_id not in question_ids for answer in self.answers):
            raise ValueError("answer references a question outside the session")
        if any(
            candidate.project_id != self.project_id
            or (
                candidate.source_answer_id is not None
                and candidate.source_answer_id not in answer_ids
            )
            for candidate in self.candidate_facts
        ):
            raise ValueError("candidate has invalid project or source-answer provenance")
        if any(decision.candidate_fact_id not in candidate_ids for decision in self.decisions):
            raise ValueError("decision references a candidate outside the session")
        return self


class ProjectState(FrozenModel):
    project_id: Identifier
    facts: tuple[CanonicalFact, ...] = ()
    applied_event_ids: tuple[Identifier, ...] = ()
    last_sequence: int = 0

    def fact(self, subject_id: str, attribute: str) -> CanonicalFact | None:
        return next(
            (
                fact
                for fact in self.facts
                if fact.subject_id == subject_id and fact.attribute == attribute
            ),
            None,
        )


def decide_candidate(
    *,
    project: Project,
    candidate: CandidateFact,
    validation: CandidateValidation,
    deciding_actor: Actor,
    decision: CandidateDecisionKind,
    decision_id: str,
    decided_at: datetime,
    rationale: str,
    next_event_id: str | None = None,
    next_sequence: int | None = None,
) -> tuple[CandidateDecision, DomainEvent | None]:
    """Record an authorized human decision and emit an event for acceptance."""

    if candidate.project_id != project.project_id:
        raise ValueError("candidate belongs to a different project")
    if deciding_actor.role is not ActorRole.HUMAN_ACCEPTANCE_AUTHORITY:
        raise PermissionError("only the human acceptance authority may review candidates")
    if deciding_actor.actor_id != project.acceptance_authority_principal_id:
        raise PermissionError("actor is not this project's acceptance authority")
    if validation.candidate_fact_id != candidate.candidate_fact_id:
        raise ValueError("validation describes a different candidate")

    if decision is CandidateDecisionKind.REJECTED:
        record = CandidateDecision(
            decision_id=decision_id,
            candidate_fact_id=candidate.candidate_fact_id,
            decision=decision,
            decided_by_actor_id=deciding_actor.actor_id,
            decided_at=decided_at,
            validation=validation,
            rationale=rationale,
        )
        return record, None

    if not validation.is_valid:
        raise ValueError("an invalid candidate cannot be accepted")
    if next_event_id is None or next_sequence is None:
        raise ValueError("acceptance requires an explicit event identity and sequence")
    event = DomainEvent(
        event_id=next_event_id,
        project_id=project.project_id,
        sequence=next_sequence,
        occurred_at=decided_at,
        actor_id=deciding_actor.actor_id,
        candidate_fact_id=candidate.candidate_fact_id,
        subject_id=candidate.subject_id,
        attribute=candidate.attribute,
        value=candidate.proposed_value,
        evidence_ids=candidate.evidence_ids,
    )
    record = CandidateDecision(
        decision_id=decision_id,
        candidate_fact_id=candidate.candidate_fact_id,
        decision=decision,
        decided_by_actor_id=deciding_actor.actor_id,
        decided_at=decided_at,
        validation=validation,
        rationale=rationale,
        resulting_domain_event_id=event.event_id,
    )
    return record, event


def replay_project(
    project: Project,
    accepted_records: tuple[AcceptedFactRecord, ...],
) -> ProjectState:
    """Rebuild state from complete, validated candidate-decision-event records."""

    facts: dict[tuple[str, str], CanonicalFact] = {}
    event_ids: set[str] = set()
    expected_sequence = 1
    for record in accepted_records:
        event = record.event
        if event.project_id != project.project_id:
            raise ValueError("event belongs to a different project")
        if record.candidate.project_id != project.project_id:
            raise ValueError("candidate belongs to a different project")
        if event.actor_id != project.acceptance_authority_principal_id:
            raise ValueError("event was not produced by the project's acceptance authority")
        if record.decision.decided_by_actor_id != project.acceptance_authority_principal_id:
            raise ValueError("decision was not made by the project's acceptance authority")
        if event.event_id in event_ids:
            raise ValueError("duplicate event identity")
        if event.sequence != expected_sequence:
            raise ValueError("event log must have contiguous sequence numbers starting at one")
        event_ids.add(event.event_id)
        expected_sequence += 1
        facts[(event.subject_id, event.attribute)] = CanonicalFact(
            subject_id=event.subject_id,
            attribute=event.attribute,
            value=event.value,
            source_candidate_fact_id=event.candidate_fact_id,
            accepted_by_actor_id=event.actor_id,
            accepted_at=event.occurred_at,
            evidence_ids=event.evidence_ids,
        )
    ordered_facts = tuple(facts[key] for key in sorted(facts))
    return ProjectState(
        project_id=project.project_id,
        facts=ordered_facts,
        applied_event_ids=tuple(record.event.event_id for record in accepted_records),
        last_sequence=len(accepted_records),
    )


def _require_absolute(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


def _require_finite_value(value: FactValue) -> None:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("fact values must be finite")


def _unique_ids(models: tuple[BaseModel, ...], attribute: str, label: str) -> set[str]:
    values = [str(getattr(model, attribute)) for model in models]
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} identity")
    return set(values)
