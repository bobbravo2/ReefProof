"""Atomic-style authored-import acceptance orchestration shared by CLI and API."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from reefproof.authored_sources.review import ExternalIdentityBinding
from reefproof.authored_sources.store import AuthoredSourceStore
from reefproof.candidate_validation import validate_candidate
from reefproof.project_state import (
    AcceptedFactRecord,
    Actor,
    CandidateDecisionKind,
    decide_candidate,
)
from reefproof.project_store import ProjectStore


def accept_source_session(
    *,
    project_store: ProjectStore,
    source_store: AuthoredSourceStore,
    session_id: str,
    actor: Actor,
    accepted_at: datetime,
    rationale: str,
) -> tuple[int, int, str]:
    """Validate and accept a complete source session, then bind its external identities."""

    if not session_id.startswith("session-source-"):
        raise ValueError("bulk acceptance is limited to source review sessions")
    session = project_store.load_session(session_id)
    if session.decisions:
        raise ValueError("source review session already contains decisions")
    if len(session.attachment_evidence_ids) != 1:
        raise ValueError("source review session must reference one source snapshot")
    evidence_id = session.attachment_evidence_ids[0]
    prefix = "evidence-source-"
    if not evidence_id.startswith(prefix):
        raise ValueError("source review evidence identity is invalid")
    snapshot_id = evidence_id.removeprefix(prefix)
    batch = source_store.load_import_for_snapshot(session.project_id, snapshot_id)
    configuration = source_store.source_configuration_for_import(
        session.project_id, batch.import_batch_id
    )
    project = project_store.load_project(session.project_id)
    start_sequence = project_store.replay(project.project_id).last_sequence + 1
    records: list[AcceptedFactRecord] = []
    for offset, candidate in enumerate(session.candidate_facts):
        validation = validate_candidate(candidate, validated_at=accepted_at)
        if not validation.is_valid:
            raise ValueError(
                f"candidate failed deterministic validation: {candidate.candidate_fact_id}"
            )
        identity = uuid5(
            NAMESPACE_URL,
            f"{session_id}:{candidate.candidate_fact_id}:{accepted_at.isoformat()}",
        ).hex
        decision, event = decide_candidate(
            project=project,
            candidate=candidate,
            validation=validation,
            deciding_actor=actor,
            decision=CandidateDecisionKind.ACCEPTED,
            decision_id=f"decision-{identity}",
            decided_at=accepted_at,
            rationale=rationale,
            next_event_id=f"event-{identity}",
            next_sequence=start_sequence + offset,
        )
        assert event is not None
        records.append(AcceptedFactRecord(candidate=candidate, decision=decision, event=event))
    identity_values = {
        (candidate.subject_id, candidate.attribute): str(candidate.proposed_value)
        for candidate in session.candidate_facts
        if candidate.attribute in {"identity.external_id", "identity.external_namespace"}
    }
    binding_subjects = sorted(
        {
            subject_id
            for subject_id, attribute in identity_values
            if attribute == "identity.external_id"
        }
    )
    bindings = tuple(
        ExternalIdentityBinding(
            binding_id=(
                "binding-"
                + uuid5(
                    NAMESPACE_URL,
                    f"{session.project_id}:{configuration.spreadsheet_id}:"
                    f"{identity_values[(subject_id, 'identity.external_namespace')]}:"
                    f"{identity_values[(subject_id, 'identity.external_id')]}",
                ).hex
            ),
            project_id=session.project_id,
            source_instance=configuration.spreadsheet_id,
            namespace=identity_values[(subject_id, "identity.external_namespace")],
            value=identity_values[(subject_id, "identity.external_id")],
            canonical_subject_id=subject_id,
            import_batch_id=batch.import_batch_id,
            accepted_at=accepted_at,
        )
        for subject_id in binding_subjects
    )
    # Preflight uniqueness before canonical mutation. record_bindings remains
    # idempotent if a process is restarted after canonical acceptance.
    existing = {
        (item.source_system, item.source_instance, item.namespace, item.value): item
        for item in source_store.list_bindings(session.project_id)
    }
    for binding in bindings:
        previous = existing.get(
            (
                binding.source_system,
                binding.source_instance,
                binding.namespace,
                binding.value,
            )
        )
        if previous is not None and previous.canonical_subject_id != binding.canonical_subject_id:
            raise ValueError("external identity is already bound to another subject")
    project_store.record_accepted_facts(session_id, tuple(records))
    source_store.record_bindings(bindings)
    return len(records), start_sequence + len(records) - 1, batch.import_batch_id


def reject_source_session(
    *,
    project_store: ProjectStore,
    session_id: str,
    actor: Actor,
    rejected_at: datetime,
    rationale: str,
) -> int:
    """Validate and atomically reject every candidate in one source session."""

    if not session_id.startswith("session-source-"):
        raise ValueError("bulk rejection is limited to source review sessions")
    session = project_store.load_session(session_id)
    if session.decisions:
        raise ValueError("source review session already contains decisions")
    project = project_store.load_project(session.project_id)
    records = []
    for candidate in session.candidate_facts:
        validation = validate_candidate(candidate, validated_at=rejected_at)
        identity = uuid5(
            NAMESPACE_URL,
            f"reject:{session_id}:{candidate.candidate_fact_id}:{rejected_at.isoformat()}",
        ).hex
        decision, event = decide_candidate(
            project=project,
            candidate=candidate,
            validation=validation,
            deciding_actor=actor,
            decision=CandidateDecisionKind.REJECTED,
            decision_id=f"decision-{identity}",
            decided_at=rejected_at,
            rationale=rationale,
        )
        assert event is None
        records.append((candidate, decision))
    project_store.record_rejections(session_id, tuple(records))
    return len(records)
