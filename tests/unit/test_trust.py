from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reefproof.project_state import PROJECT_ID, Project
from reefproof.project_store import ProjectStore
from reefproof.storage import Database
from reefproof.trust import (
    ProjectionDependency,
    TrustEvent,
    TrustRootFact,
    TrustScopeKind,
    TrustStatus,
    apply_trust,
    replay_trust,
    revoked_projection_ids,
)

NOW = datetime(2026, 7, 25, 20, tzinfo=UTC)
ROOT = TrustRootFact(
    subject_id="return_pump",
    attribute="physical.elevation_inches",
    evidence_ids=("evidence-return-flow",),
    source_candidate_fact_id="candidate-return-flow",
)


def _revocation(sequence: int = 1) -> TrustEvent:
    return TrustEvent(
        trust_event_id=f"trust-00000000-0000-4000-8000-{sequence:012d}",
        project_id=PROJECT_ID,
        sequence=sequence,
        event_type="revoked",
        occurred_at=NOW,
        actor_id="acceptance-authority",
        rationale="The measurement chain is no longer trustworthy.",
        scope_kind=TrustScopeKind.EVIDENCE,
        scope_id="evidence-return-flow",
        affected_roots=(ROOT,),
        totp_verified_at=NOW,
    )


def test_replay_is_append_only_and_rejects_duplicate_active_scope() -> None:
    state = replay_trust(PROJECT_ID, (_revocation(),))
    assert state.active_revocations == (_revocation(),)
    with pytest.raises(ValueError, match="duplicate active revocation"):
        replay_trust(PROJECT_ID, (_revocation(), _revocation(2)))


def test_projection_propagation_is_transitive_and_preserves_raw_state() -> None:
    declarations = (
        ProjectionDependency(
            projection_id="rule:return-flow",
            evidence_ids=("evidence-return-flow",),
            subject_ids=("return_pump",),
        ),
        ProjectionDependency(
            projection_id="overview:posture",
            projection_dependencies=("rule:return-flow",),
        ),
        ProjectionDependency(projection_id="rule:temperature"),
    )
    assert revoked_projection_ids(declarations, (_revocation(),)) == (
        "overview:posture",
        "rule:return-flow",
    )
    effective = apply_trust(
        declaration=declarations[0],
        evaluated_state="PASS",
        active_revocations=(_revocation(),),
        declarations=declarations,
    )
    assert effective.evaluated_state == "PASS"
    assert effective.state == "UNKNOWN"
    assert effective.trust_status is TrustStatus.REVOKED


def test_projection_cycles_fail_closed() -> None:
    declarations = (
        ProjectionDependency(projection_id="a", projection_dependencies=("b",)),
        ProjectionDependency(projection_id="b", projection_dependencies=("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        revoked_projection_ids(declarations, (_revocation(),))


def test_schema_0006_persists_and_protects_trust_events(tmp_path: Path) -> None:
    path = tmp_path / "reefproof.sqlite3"
    database = Database(path)
    database.migrate()
    store = ProjectStore(path)
    store.ensure_project(
        Project(
            project_id=PROJECT_ID,
            acceptance_authority_principal_id="acceptance-authority",
            created_at=NOW,
        )
    )
    store.append_trust_event(_revocation())
    assert store.replay_trust(PROJECT_ID).active_revocations == (_revocation(),)
    counts = database.inspect_evidence()["counts"]
    assert isinstance(counts, dict)
    assert counts["project_trust_events"] == 1
    with (
        sqlite3.connect(path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="immutable"),
    ):
        connection.execute(
            "UPDATE project_trust_events SET scope_id = scope_id WHERE trust_event_id = ?",
            (_revocation().trust_event_id,),
        )
