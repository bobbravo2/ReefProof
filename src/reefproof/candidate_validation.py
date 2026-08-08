"""Deterministic candidate validation registry for the primary v0.1 project."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from reefproof.physical_proposals import validate_physical_candidate_fact
from reefproof.project_state import CandidateFact, CandidateValidation


class CandidateValidationReason(StrEnum):
    DOMAIN_VALIDATOR_NOT_REGISTERED = "domain_validator_not_registered"
    PHYSICAL_CANDIDATE_INVALID = "physical_candidate_invalid"


def validate_candidate(
    candidate: CandidateFact,
    *,
    validated_at: datetime,
) -> CandidateValidation:
    """Validate a typed candidate using only registered deterministic rules."""

    if candidate.attribute.startswith("physical."):
        try:
            validate_physical_candidate_fact(candidate)
        except ValueError:
            return CandidateValidation(
                candidate_fact_id=candidate.candidate_fact_id,
                schema_valid=True,
                domain_valid=False,
                reason_codes=(CandidateValidationReason.PHYSICAL_CANDIDATE_INVALID.value,),
                validated_at=validated_at,
            )
        return CandidateValidation(
            candidate_fact_id=candidate.candidate_fact_id,
            schema_valid=True,
            domain_valid=True,
            reason_codes=(),
            validated_at=validated_at,
        )
    return CandidateValidation(
        candidate_fact_id=candidate.candidate_fact_id,
        schema_valid=True,
        domain_valid=False,
        reason_codes=(CandidateValidationReason.DOMAIN_VALIDATOR_NOT_REGISTERED.value,),
        validated_at=validated_at,
    )
