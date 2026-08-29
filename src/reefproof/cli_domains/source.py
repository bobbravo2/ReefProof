"""Read-only authored-source validation commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer


def _configured_source():
    import reefproof.cli as cli
    from reefproof.authored_sources import (
        GoogleServiceAccountCredentialProvider,
        GoogleSheetsSource,
    )

    settings = cli.load_settings()
    source = settings.authored_sources.google_sheets
    if not source.enabled or source.spreadsheet_id is None or source.credential_file is None:
        raise ValueError("configure and enable authored_sources.google_sheets before validation")
    return GoogleSheetsSource(
        spreadsheet_id=source.spreadsheet_id,
        source_alias=source.source_alias,
        credentials=GoogleServiceAccountCredentialProvider(source.credential_file),
    )


def register(source_app: typer.Typer) -> None:
    @source_app.command("validate")
    def source_validate() -> None:
        """Fetch and validate the configured Sheet without persisting or accepting it."""

        import reefproof.cli as cli
        from reefproof.authored_sources import import_candidates, normalize_source_snapshot

        try:
            snapshot = _configured_source().fetch()
            batch = normalize_source_snapshot(snapshot)
            candidates = (
                ()
                if not batch.valid
                else import_candidates(
                    batch,
                    project_id=cli.load_settings().project.project_id,
                    proposed_by_actor_id="source-parser",
                    proposed_at=snapshot.fetched_at,
                )
            )
        except Exception as error:
            typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
            raise typer.Exit(code=2) from error
        document = {
            "diagnostics": [item.model_dump(mode="json") for item in batch.diagnostics],
            "candidate_count": len(candidates),
            "fetched_at": snapshot.fetched_at.isoformat(),
            "normalized_content_hash": batch.normalized_content_hash,
            "record_counts": {name.value: count for name, count in batch.record_counts.items()},
            "snapshot_hash": snapshot.snapshot_hash,
            "source_alias": snapshot.source_alias,
            "spreadsheet_title": snapshot.spreadsheet_title,
            "status": "VALID" if batch.valid else "INVALID",
            "tabs": [tab.name.value for tab in snapshot.tabs],
        }
        typer.echo(json.dumps(document, indent=2, sort_keys=True))
        if not batch.valid:
            raise typer.Exit(code=2)

    @source_app.command("load")
    def source_load() -> None:
        """Persist one validated import and noncanonical candidates for human review."""

        import reefproof.cli as cli
        from reefproof.authored_sources import (
            AuthoredSourceStore,
            load_authored_source,
        )
        from reefproof.project_store import ProjectStore

        try:
            settings = cli.load_settings(create_data_directory=True)
            database_path = cli.database_path(settings.data_directory)
            database = cli.Database(database_path)
            database.migrate()
            project_store = ProjectStore(database_path)
            loaded = load_authored_source(
                source=_configured_source(),
                source_store=AuthoredSourceStore(database_path),
                project_store=project_store,
                project_id=settings.project.project_id,
                project_name=settings.project.display_name,
                acceptance_authority_principal_id=(
                    settings.project.acceptance_authority_principal_id
                ),
                freshness_seconds=settings.authored_sources.google_sheets.freshness_seconds,
            )
        except Exception as error:
            typer.echo(json.dumps({"error": str(error), "status": "INVALID"}, sort_keys=True))
            raise typer.Exit(code=2) from error
        if not loaded.batch.valid:
            typer.echo(
                json.dumps(
                    {
                        "candidate_count": 0,
                        "canonical_fact_count": len(
                            project_store.replay(settings.project.project_id).facts
                        ),
                        "diagnostics": [
                            item.model_dump(mode="json") for item in loaded.batch.diagnostics
                        ],
                        "import_batch_id": loaded.batch.import_batch_id,
                        "inserted": loaded.inserted,
                        "status": "INVALID",
                    },
                    sort_keys=True,
                )
            )
            raise typer.Exit(code=2)
        typer.echo(
            json.dumps(
                {
                    "candidate_count": loaded.candidate_count,
                    "canonical_fact_count": len(
                        project_store.replay(settings.project.project_id).facts
                    ),
                    "import_batch_id": loaded.batch.import_batch_id,
                    "inserted": loaded.inserted,
                    "session_id": loaded.session_id,
                    "status": "PENDING_REVIEW",
                },
                sort_keys=True,
            )
        )

    @source_app.command("review")
    def source_review(
        session_id: Annotated[
            str,
            typer.Argument(help="Source review session returned by source load."),
        ],
    ) -> None:
        """Render the persisted semantic diff and cell provenance before acceptance."""

        import reefproof.cli as cli
        from reefproof.authored_sources import AuthoredSourceStore, build_import_review
        from reefproof.project_store import ProjectStore

        try:
            settings = cli.load_settings()
            database_path = cli.database_path(settings.data_directory)
            project_store = ProjectStore(database_path)
            source_store = AuthoredSourceStore(database_path)
            session = project_store.load_session(session_id)
            if not session_id.startswith("session-source-"):
                raise ValueError("review is limited to source import sessions")
            if len(session.attachment_evidence_ids) != 1:
                raise ValueError("source review session must reference one source snapshot")
            evidence_id = session.attachment_evidence_ids[0]
            if not evidence_id.startswith("evidence-source-"):
                raise ValueError("source review evidence identity is invalid")
            batch = source_store.load_import_for_snapshot(
                session.project_id,
                evidence_id.removeprefix("evidence-source-"),
            )
            configuration = source_store.source_configuration_for_import(
                session.project_id, batch.import_batch_id
            )
            review = build_import_review(
                batch,
                project_id=session.project_id,
                state=project_store.replay(session.project_id),
                bindings=source_store.list_bindings(session.project_id),
                source_instance=configuration.spreadsheet_id,
            )
        except Exception as error:
            typer.echo(json.dumps({"error": str(error), "status": "FAIL"}, sort_keys=True))
            raise typer.Exit(code=2) from error
        document = review.model_dump(mode="json")
        document["session_id"] = session_id
        document["status"] = "READY_FOR_DECISION" if review.valid else "INVALID"
        typer.echo(json.dumps(document, indent=2, sort_keys=True))

    @source_app.command("accept")
    def source_accept(
        session_id: Annotated[str, typer.Argument(help="Source review session from source load.")],
        totp_code: Annotated[
            str,
            typer.Option("--totp-code", help="Fresh six-digit acceptance-authority code."),
        ],
        rationale: Annotated[
            str,
            typer.Option("--rationale", help="Human rationale applied to this reviewed batch."),
        ],
    ) -> None:
        """Atomically accept every valid candidate in one source review session."""

        import reefproof.cli as cli
        from reefproof.authored_sources import AuthoredSourceStore
        from reefproof.authored_sources.acceptance import accept_source_session
        from reefproof.project_state import Actor, ActorRole
        from reefproof.project_store import ProjectStore

        try:
            settings = cli.load_settings(create_data_directory=True)
            verified_at = cli.TotpState(
                settings.data_directory / "operator-totp.json",
                principal_id=settings.project.acceptance_authority_principal_id,
            ).verify(totp_code)
            store = ProjectStore(cli.database_path(settings.data_directory))
            actor = Actor(
                actor_id=settings.project.acceptance_authority_principal_id,
                display_name=settings.project.acceptance_authority_display_name,
                role=ActorRole.HUMAN_ACCEPTANCE_AUTHORITY,
            )
            accepted_count, project_sequence, import_batch_id = accept_source_session(
                project_store=store,
                source_store=AuthoredSourceStore(cli.database_path(settings.data_directory)),
                session_id=session_id,
                actor=actor,
                accepted_at=verified_at,
                rationale=rationale,
            )
        except Exception as error:
            typer.echo(json.dumps({"error": str(error), "status": "FAIL"}, sort_keys=True))
            raise typer.Exit(code=2) from error
        typer.echo(
            json.dumps(
                {
                    "accepted_candidate_count": accepted_count,
                    "import_batch_id": import_batch_id,
                    "project_sequence": project_sequence,
                    "session_id": session_id,
                    "status": "ACCEPTED",
                },
                sort_keys=True,
            )
        )
