from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from reefproof.physical import mock_collective_physical_twin
from reefproof.physical_proposals import (
    PhysicalAttribute,
    PhysicalModelProposal,
    PhysicalTarget,
    SupportedPhysicalType,
    physical_proposal_candidate,
)
from reefproof.project_state import (
    AcceptedFactRecord,
    Actor,
    ActorRole,
    CandidateDecisionKind,
    CandidateValidation,
    Project,
    decide_candidate,
    replay_project,
)

NOW = datetime(2026, 7, 25, 22, 0, tzinfo=UTC)


def proposal(**changes: object) -> PhysicalModelProposal:
    values: dict[str, object] = {
        "proposal_id": "physical-proposal-return-height",
        "target_entity_id": PhysicalTarget.RETURN_PUMP,
        "attribute": PhysicalAttribute.ELEVATION_INCHES,
        "proposed_value": 6.0,
        "proposed_by_actor_id": "reefproof-agent",
        "proposed_at": NOW,
        "source_answer_id": "answer-return-height",
        "evidence_ids": ("evidence-mock-photo",),
    }
    values.update(changes)
    return PhysicalModelProposal.model_validate(values)


def project() -> Project:
    return Project(
        acceptance_authority_principal_id="acceptance-authority",
        created_at=NOW,
    )


def authority() -> Actor:
    return Actor(
        actor_id="acceptance-authority",
        display_name="Acceptance authority",
        role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
    )


def test_proposal_converts_to_attributable_candidate_without_mutating_twin() -> None:
    twin = mock_collective_physical_twin()
    before = twin.model_dump_json()

    candidate = physical_proposal_candidate(twin, proposal())

    assert twin.model_dump_json() == before
    assert candidate.epistemic_state == "candidate"
    assert candidate.project_id == "primary-reef-system"
    assert candidate.subject_id == "return_pump"
    assert candidate.attribute == "physical.elevation_inches"
    assert candidate.proposed_value == 6.0
    assert candidate.proposed_by_actor_id == "reefproof-agent"
    assert candidate.source_answer_id == "answer-return-height"
    assert candidate.evidence_ids == ("evidence-mock-photo",)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        (PhysicalAttribute.PHYSICAL_TYPE, SupportedPhysicalType.RETURN_PUMP),
        (PhysicalAttribute.QUANTITY, 2),
        (PhysicalAttribute.ELEVATION_INCHES, 0.0),
        (PhysicalAttribute.WIDTH_INCHES, 10.0),
        (PhysicalAttribute.HEIGHT_INCHES, 8.0),
        (PhysicalAttribute.DEPTH_INCHES, 6.0),
        (PhysicalAttribute.VOLUME_GALLONS, 120.0),
    ],
)
def test_finite_supported_attribute_vocabulary(
    attribute: PhysicalAttribute,
    value: SupportedPhysicalType | int | float,
) -> None:
    candidate = physical_proposal_candidate(
        mock_collective_physical_twin(),
        proposal(attribute=attribute, proposed_value=value),
    )

    assert candidate.attribute == f"physical.{attribute.value}"


@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": "another-project"},
        {"collective_name": "Live Collective"},
        {"provenance_label": "LIVE"},
        {"live_observation": True},
        {"target_entity_id": "RP.DEVICE.0123456789abcdef"},
        {"attribute": "controller.output_mode"},
        {"attribute": PhysicalAttribute.PHYSICAL_TYPE, "proposed_value": "controller"},
        {"attribute": PhysicalAttribute.QUANTITY, "proposed_value": 1.5},
        {"attribute": PhysicalAttribute.ELEVATION_INCHES, "proposed_value": -1.0},
        {"source_answer_id": None, "evidence_ids": ()},
        {"evidence_ids": ("hydros-device-123",)},
        {"hydros_device_id": "private-controller-id"},
    ],
)
def test_rejects_live_private_arbitrary_and_controller_semantics(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        proposal(**changes)


def test_only_project_authority_acceptance_can_create_canonical_event() -> None:
    candidate = physical_proposal_candidate(mock_collective_physical_twin(), proposal())
    validation = CandidateValidation(
        candidate_fact_id=candidate.candidate_fact_id,
        schema_valid=True,
        domain_valid=True,
        reason_codes=(),
        validated_at=NOW,
    )
    agent = Actor(
        actor_id="reefproof-agent",
        display_name="ReefProof Agent",
        role=ActorRole.AGENT,
    )

    with pytest.raises(PermissionError, match="only the human acceptance authority"):
        decide_candidate(
            project=project(),
            candidate=candidate,
            validation=validation,
            deciding_actor=agent,
            decision=CandidateDecisionKind.ACCEPTED,
            decision_id="decision-agent-physical",
            decided_at=NOW,
            rationale="Agent cannot approve its proposal.",
            next_event_id="event-agent-physical",
            next_sequence=1,
        )

    decision, event = decide_candidate(
        project=project(),
        candidate=candidate,
        validation=validation,
        deciding_actor=authority(),
        decision=CandidateDecisionKind.ACCEPTED,
        decision_id="decision-authority-physical",
        decided_at=NOW,
        rationale="the acceptance authority confirmed the authored mock dimension.",
        next_event_id="event-authority-physical",
        next_sequence=1,
    )

    assert event is not None
    record = AcceptedFactRecord(candidate=candidate, decision=decision, event=event)
    state = replay_project(project(), (record,))
    fact = state.fact("return_pump", "physical.elevation_inches")
    assert decision.resulting_domain_event_id == event.event_id
    assert fact is not None
    assert fact.value == 6.0


def test_models_are_closed_and_do_not_expose_accept_apply_or_device_operations() -> None:
    document = proposal().model_dump(mode="json")

    assert set(document) == {
        "proposal_id",
        "project_id",
        "collective_name",
        "provenance_label",
        "live_observation",
        "target_entity_id",
        "attribute",
        "proposed_value",
        "proposed_by_actor_id",
        "proposed_at",
        "source_answer_id",
        "evidence_ids",
    }
    assert not {"accept", "apply", "controller", "device_id", "output_mode"} & set(document)
