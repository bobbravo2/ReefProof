"""Typed physical-model proposals for the fixed v0.1 Mock Collective.

This module can create candidate facts only.  It cannot accept a candidate,
apply a proposal, or mutate a physical model.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reefproof.physical import PhysicalTwin
from reefproof.project_state import PROJECT_ID, CandidateFact


class PhysicalTarget(StrEnum):
    DISPLAY_TANK = "display_tank"
    SUMP = "sump"
    RETURN_PUMP = "return_pump"


class SupportedPhysicalType(StrEnum):
    DISPLAY_TANK = "display_tank"
    SUMP = "sump"
    RETURN_PUMP = "return_pump"


class PhysicalAttribute(StrEnum):
    PHYSICAL_TYPE = "physical_type"
    QUANTITY = "quantity"
    ELEVATION_INCHES = "elevation_inches"
    WIDTH_INCHES = "size.width_inches"
    HEIGHT_INCHES = "size.height_inches"
    DEPTH_INCHES = "size.depth_inches"
    VOLUME_GALLONS = "size.volume_gallons"


PhysicalProposalValue = SupportedPhysicalType | int | float


class PhysicalModelProposal(BaseModel):
    """One attributable, non-live candidate refinement."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: str = Field(pattern=r"^physical-proposal-[a-z0-9_-]+$")
    project_id: Literal["primary-reef-system"] = PROJECT_ID
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    target_entity_id: PhysicalTarget
    attribute: PhysicalAttribute
    proposed_value: PhysicalProposalValue
    proposed_by_actor_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    proposed_at: datetime
    source_answer_id: str | None = Field(
        default=None,
        pattern=r"^answer-[a-z0-9_-]+$",
    )
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_mock_candidate(self) -> Self:
        if self.project_id != PROJECT_ID:
            raise ValueError("physical proposals are limited to the primary v0.1 project")
        if self.collective_name != "Mock Collective":
            raise ValueError("physical proposals are limited to Mock Collective")
        if self.provenance_label != "MANUAL / NOT LIVE" or self.live_observation:
            raise ValueError("physical proposals must remain MANUAL / NOT LIVE")
        if self.proposed_at.tzinfo is None or self.proposed_at.utcoffset() is None:
            raise ValueError("proposed_at must include a timezone")
        if self.source_answer_id is None and not self.evidence_ids:
            raise ValueError("physical proposal requires source provenance")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("physical proposal evidence identities must be unique")
        if any(not _is_safe_source_id(evidence_id) for evidence_id in self.evidence_ids):
            raise ValueError("physical proposal contains an invalid source identity")
        _validate_attribute_value(self.attribute, self.proposed_value)
        return self


def physical_proposal_candidate(
    twin: PhysicalTwin,
    proposal: PhysicalModelProposal,
) -> CandidateFact:
    """Validate a target in the fixed mock twin and return a non-canonical fact."""

    if (
        twin.collective_name != "Mock Collective"
        or twin.provenance_label != "MANUAL / NOT LIVE"
        or twin.live_observation
    ):
        raise ValueError("physical proposals require the fixed non-live Mock Collective")
    known_entity_ids = {entity.entity_id for entity in twin.entities}
    if proposal.target_entity_id.value not in known_entity_ids:
        raise ValueError("physical proposal target does not exist in the mock twin")
    return CandidateFact(
        candidate_fact_id=f"candidate-{proposal.proposal_id}",
        project_id=proposal.project_id,
        subject_id=proposal.target_entity_id.value,
        attribute=f"physical.{proposal.attribute.value}",
        proposed_value=proposal.proposed_value.value
        if isinstance(proposal.proposed_value, SupportedPhysicalType)
        else proposal.proposed_value,
        proposed_by_actor_id=proposal.proposed_by_actor_id,
        proposed_at=proposal.proposed_at,
        source_answer_id=proposal.source_answer_id,
        evidence_ids=proposal.evidence_ids,
    )


def validate_physical_candidate_fact(candidate: CandidateFact) -> None:
    """Revalidate a persisted physical candidate without trusting client claims."""

    if candidate.project_id != PROJECT_ID:
        raise ValueError("physical candidate belongs to a different project")
    try:
        target = PhysicalTarget(candidate.subject_id)
        attribute = PhysicalAttribute(candidate.attribute.removeprefix("physical."))
    except ValueError as error:
        raise ValueError("unsupported physical candidate target or attribute") from error
    if candidate.attribute != f"physical.{attribute.value}":
        raise ValueError("physical candidate attribute must use the physical namespace")
    if candidate.source_answer_id is None and not candidate.evidence_ids:
        raise ValueError("physical candidate requires source provenance")
    if target.value != candidate.subject_id:
        raise ValueError("physical candidate target identity is not canonical")
    value: PhysicalProposalValue
    if attribute is PhysicalAttribute.PHYSICAL_TYPE:
        try:
            value = SupportedPhysicalType(candidate.proposed_value)
        except (TypeError, ValueError) as error:
            raise ValueError("physical_type requires a supported physical type") from error
    else:
        if isinstance(candidate.proposed_value, bool) or not isinstance(
            candidate.proposed_value, (int, float)
        ):
            raise ValueError(f"{attribute.value} requires a numeric value")
        value = candidate.proposed_value
    _validate_attribute_value(attribute, value)


def _validate_attribute_value(
    attribute: PhysicalAttribute,
    value: PhysicalProposalValue,
) -> None:
    if attribute is PhysicalAttribute.PHYSICAL_TYPE:
        if not isinstance(value, SupportedPhysicalType):
            raise ValueError("physical_type requires a supported physical type")
        return
    if isinstance(value, (SupportedPhysicalType, bool)):
        raise ValueError(f"{attribute.value} requires a numeric value")
    if attribute is PhysicalAttribute.QUANTITY:
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("quantity must be an integer from 1 through 100")
        return
    number = float(value)
    if attribute is PhysicalAttribute.ELEVATION_INCHES:
        if not 0 <= number <= 500:
            raise ValueError("elevation_inches must be from 0 through 500")
    elif not 0 < number <= 10_000:
        raise ValueError(f"{attribute.value} must be greater than 0 and at most 10000")


def _is_safe_source_id(value: str) -> bool:
    if not value or not value.startswith(("answer-", "evidence-")):
        return False
    return all(
        character.islower() or character.isdigit() or character in "_-" for character in value
    )
