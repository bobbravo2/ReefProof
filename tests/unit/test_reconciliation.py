from datetime import UTC, datetime
from pathlib import Path

from reefproof.authored_sources import ExternalIdentityBinding
from reefproof.configuration import snapshot_hydros_export
from reefproof.project_state import CanonicalFact, ProjectState
from reefproof.reconciliation import ReconciliationState, reconciliation_projection

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
DEVICE = "rp:primary-reef-system:device:dev-1"
FIXTURE = Path("tests/fixtures/configuration/hydros-download-config-sanitized.json")


def _state() -> ProjectState:
    return ProjectState(
        project_id="primary-reef-system",
        facts=(
            CanonicalFact(
                subject_id=DEVICE,
                attribute="identity.external_id",
                value="DEV-1",
                source_candidate_fact_id="candidate-device",
                accepted_at=NOW,
                accepted_by_actor_id="acceptance-authority",
                evidence_ids=("evidence-device",),
            ),
        ),
        applied_event_ids=("event-device",),
        last_sequence=1,
    )


def test_reconciliation_never_matches_names_without_explicit_binding() -> None:
    observed = snapshot_hydros_export(FIXTURE, captured_at=NOW)

    projection = reconciliation_projection(state=_state(), bindings=(), observed_snapshot=observed)

    assert projection.matched_count == 0
    assert projection.authored_only_count == 1
    assert projection.observed_only_count == len(observed.entities)
    assert {item.state for item in projection.items} == {
        ReconciliationState.AUTHORED_ONLY,
        ReconciliationState.OBSERVED_ONLY,
    }


def test_reconciliation_matches_only_one_explicit_hydros_identity() -> None:
    observed = snapshot_hydros_export(FIXTURE, captured_at=NOW)
    entity = observed.entities[0]
    binding = ExternalIdentityBinding(
        binding_id="binding-hydros-device",
        project_id="primary-reef-system",
        source_system="hydros",
        source_instance="observed-snapshot-fixture",
        namespace="reefproof_id",
        value=entity.reefproof_id,
        canonical_subject_id=DEVICE,
        evidence_reference="fixture observed identity review",
        rationale="Matched the sanitized observed fixture identity.",
        accepted_at=NOW,
    )

    projection = reconciliation_projection(
        state=_state(), bindings=(binding,), observed_snapshot=observed
    )

    assert projection.matched_count == 1
    assert projection.authored_only_count == 0
    assert projection.observed_only_count == len(observed.entities) - 1
    assert projection.items[0].state is ReconciliationState.MATCHED


def test_stale_explicit_binding_is_a_blocking_conflict() -> None:
    binding = ExternalIdentityBinding(
        binding_id="binding-missing-hydros-device",
        project_id="primary-reef-system",
        source_system="hydros",
        source_instance="observed-snapshot-fixture",
        namespace="vendor_id",
        value="missing-vendor-id",
        canonical_subject_id=DEVICE,
        evidence_reference="fixture observed identity review",
        rationale="The prior observed identity is no longer present.",
        accepted_at=NOW,
    )

    projection = reconciliation_projection(
        state=_state(), bindings=(binding,), observed_snapshot=None
    )

    assert projection.conflict_count == 1
    assert projection.blocking_subject_ids == (DEVICE,)
