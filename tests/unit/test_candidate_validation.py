"""Deterministic candidate validation registry tests."""

from __future__ import annotations

from datetime import UTC, datetime

from reefproof.candidate_validation import CandidateValidationReason, validate_candidate
from reefproof.project_state import PROJECT_ID, CandidateFact

NOW = datetime(2026, 7, 25, 20, tzinfo=UTC)


def _candidate(*, attribute: str, value: str | int | float | bool) -> CandidateFact:
    return CandidateFact(
        candidate_fact_id="candidate-validation-example",
        project_id=PROJECT_ID,
        subject_id="return_pump",
        attribute=attribute,
        proposed_value=value,
        proposed_by_actor_id="acceptance-authority",
        proposed_at=NOW,
        evidence_ids=("evidence-direct-observation",),
    )


def test_registered_physical_candidate_is_deterministically_valid() -> None:
    validation = validate_candidate(
        _candidate(attribute="physical.elevation_inches", value=48),
        validated_at=NOW,
    )

    assert validation.is_valid
    assert validation.reason_codes == ()


def test_invalid_physical_candidate_fails_closed() -> None:
    validation = validate_candidate(
        _candidate(attribute="physical.elevation_inches", value=-1),
        validated_at=NOW,
    )

    assert not validation.is_valid
    assert validation.reason_codes == (CandidateValidationReason.PHYSICAL_CANDIDATE_INVALID.value,)


def test_unregistered_candidate_domain_fails_closed() -> None:
    validation = validate_candidate(
        _candidate(attribute="equipment.minimum_flow_gph", value=1800),
        validated_at=NOW,
    )

    assert not validation.is_valid
    assert validation.schema_valid
    assert not validation.domain_valid
    assert validation.reason_codes == (
        CandidateValidationReason.DOMAIN_VALIDATOR_NOT_REGISTERED.value,
    )
