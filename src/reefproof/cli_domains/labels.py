"""Deterministic label CSV export commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer


def register(labels_app: typer.Typer) -> None:
    @labels_app.command("export")
    def export_labels(
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                file_okay=True,
                dir_okay=False,
                resolve_path=True,
                help=(
                    "New CSV output path; defaults to the versioned project filename in "
                    "the current directory. Existing files are never overwritten."
                ),
            ),
        ] = None,
    ) -> None:
        """Export backend-derived DEVICE, PORT, CABLE, and POWER SUPPLY labels."""

        import reefproof.cli as cli
        from reefproof.authored_sources import AuthoredSourceStore
        from reefproof.labels import (
            generate_label_manifest,
            label_export_filename,
            render_label_csv,
        )
        from reefproof.project_store import ProjectStore

        settings = cli.load_settings()
        database_path = cli.database_path(settings.data_directory)
        output = output or Path.cwd() / label_export_filename(
            settings.project.display_name,
            version=cli.__version__,
        )
        if output.exists():
            typer.echo(json.dumps({"error": "output already exists", "status": "FAIL"}))
            raise typer.Exit(code=2)
        try:
            state = ProjectStore(database_path).replay(settings.project.project_id)
            manifest = generate_label_manifest(
                state,
                project_name=settings.project.display_name,
                bindings=AuthoredSourceStore(database_path).list_bindings(
                    settings.project.project_id
                ),
            )
            if not manifest.records:
                raise ValueError("accepted canonical state produces no labels")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(render_label_csv(manifest), encoding="utf-8", newline="")
        except (OSError, ValueError, KeyError) as error:
            typer.echo(json.dumps({"error": str(error), "status": "FAIL"}, sort_keys=True))
            raise typer.Exit(code=2) from error
        typer.echo(
            json.dumps(
                {
                    "label_count": len(manifest.records),
                    "manifest_id": manifest.manifest_id,
                    "output": str(output),
                    "status": "PASS",
                },
                sort_keys=True,
            )
        )
