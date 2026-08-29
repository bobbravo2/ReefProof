"""Shared authored-source load orchestration for CLI and Workbench."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from reefproof.authored_sources.candidates import import_candidates
from reefproof.authored_sources.models import AuthoredImportBatch, AuthoredSourceConfiguration
from reefproof.authored_sources.normalize import normalize_source_snapshot
from reefproof.authored_sources.protocol import AuthoredSystemSource
from reefproof.authored_sources.store import AuthoredSourceStore
from reefproof.project_state import InterviewSession, Project
from reefproof.project_store import ProjectStore


@dataclass(frozen=True)
class LoadedAuthoredImport:
    batch: AuthoredImportBatch
    candidate_count: int
    inserted: bool
    session_id: str


def load_authored_source(
    *,
    source: AuthoredSystemSource,
    source_store: AuthoredSourceStore,
    project_store: ProjectStore,
    project_id: str,
    project_name: str,
    acceptance_authority_principal_id: str,
    freshness_seconds: int,
) -> LoadedAuthoredImport:
    """Fetch, validate, and persist review candidates without canonical mutation."""

    snapshot = source.fetch()
    batch = normalize_source_snapshot(snapshot)
    candidates = (
        import_candidates(
            batch,
            project_id=project_id,
            proposed_by_actor_id="source-parser",
            proposed_at=snapshot.fetched_at,
        )
        if batch.valid
        else ()
    )
    project_store.ensure_project(
        Project(
            project_id=project_id,
            name=project_name,
            acceptance_authority_principal_id=acceptance_authority_principal_id,
            created_at=snapshot.fetched_at,
        )
    )
    configuration = source_store.configuration_for_source(
        project_id=project_id,
        source_alias=snapshot.source_alias,
        spreadsheet_id=snapshot.spreadsheet_id,
    )
    if configuration is None:
        source_id = uuid5(
            NAMESPACE_URL,
            f"{project_id}:{snapshot.source_alias}:{snapshot.spreadsheet_id}",
        ).hex
        configuration = AuthoredSourceConfiguration(
            source_configuration_id=f"source-config-{source_id}",
            project_id=project_id,
            source_alias=snapshot.source_alias,
            spreadsheet_id=snapshot.spreadsheet_id,
            configured_at=snapshot.fetched_at,
            freshness_seconds=freshness_seconds,
        )
        source_store.record_configuration(configuration)
    inserted = source_store.record_import(
        project_id=project_id,
        source_configuration_id=configuration.source_configuration_id,
        snapshot=snapshot,
        batch=batch,
    )
    session_id = f"session-source-{batch.import_batch_id.replace('-', '')}"
    if inserted and batch.valid:
        project_store.record_session(
            InterviewSession(
                session_id=session_id,
                project_id=project_id,
                initiated_by_actor_id="source-parser",
                initiated_at=snapshot.fetched_at,
                purpose=f"Review authored import {batch.import_batch_id}",
                scope_subject_ids=tuple(sorted({candidate.subject_id for candidate in candidates})),
                attachment_evidence_ids=(
                    f"evidence-source-{snapshot.source_snapshot_id.casefold()}",
                ),
            )
        )
        for candidate in candidates:
            project_store.record_candidate(session_id, candidate)
    return LoadedAuthoredImport(
        batch=batch,
        candidate_count=len(candidates),
        inserted=inserted,
        session_id=session_id,
    )
