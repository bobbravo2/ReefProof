"""Database administration CLI commands."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import typer


def register(database_app: typer.Typer) -> None:
    @database_app.command("schema")
    def storage_schema() -> None:
        """Report local SQLite schema and journal state without creating a database."""

        import reefproof.cli as cli

        path = cli.database_path(cli.load_settings().data_directory)
        if not path.is_file():
            typer.echo(
                json.dumps(
                    {
                        "database": str(path),
                        "database_filename": cli.DATABASE_FILENAME,
                        "initialized": False,
                        "schema_version": 0,
                    },
                    sort_keys=True,
                )
            )
            return
        try:
            database = cli.Database(path)
            document = {
                "database": str(path),
                "database_filename": cli.DATABASE_FILENAME,
                "initialized": True,
                "journal_mode": database.journal_mode(),
                "schema_version": database.schema_version(),
            }
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(json.dumps({"database": str(path), "error": str(error), "status": "FAIL"}))
            raise typer.Exit(code=2) from error
        typer.echo(json.dumps(document, sort_keys=True))

    @database_app.command("verify")
    def storage_verify() -> None:
        """Check SQLite integrity and report whether local evidence storage is readable."""

        import reefproof.cli as cli

        path = cli.database_path(cli.load_settings().data_directory)
        if not path.is_file():
            typer.echo(
                json.dumps({"database": str(path), "status": "UNINITIALIZED"}, sort_keys=True)
            )
            raise typer.Exit(code=2)
        try:
            database = cli.Database(path)
            integrity = database.integrity_check()
            document = {
                "database": str(path),
                "integrity": integrity,
                "journal_mode": database.journal_mode(),
                "schema_version": database.schema_version(),
                "status": "PASS" if integrity == "ok" else "FAIL",
            }
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(json.dumps({"database": str(path), "error": str(error), "status": "FAIL"}))
            raise typer.Exit(code=2) from error
        typer.echo(json.dumps(document, sort_keys=True))
        if integrity != "ok":
            raise typer.Exit(code=2)

    @database_app.command("inspect")
    def storage_inspect() -> None:
        """Read fixed evidence projections without accepting SQL or modifying storage."""

        import reefproof.cli as cli

        path = cli.database_path(cli.load_settings().data_directory)
        if not path.is_file():
            typer.echo(
                json.dumps({"database": str(path), "status": "UNINITIALIZED"}, sort_keys=True)
            )
            raise typer.Exit(code=2)
        try:
            document = cli.Database(path).inspect_evidence()
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(
                json.dumps(
                    {"database": str(path), "error": str(error), "status": "FAIL"},
                    sort_keys=True,
                )
            )
            raise typer.Exit(code=2) from error
        typer.echo(
            json.dumps(
                {"database": str(path), "status": "PASS", **document},
                sort_keys=True,
            )
        )

    @database_app.command("backup")
    def storage_backup(
        destination: Annotated[
            Path | None,
            typer.Argument(
                help="Optional new SQLite path; omit to use the configured rotating backup root."
            ),
        ] = None,
        root: Annotated[
            Path | None,
            typer.Option(
                "--root",
                help="One-time backup root used to generate the dated destination.",
            ),
        ] = None,
    ) -> None:
        """Create an atomic SQLite-consistent backup, including committed WAL state."""

        import reefproof.cli as cli

        settings = cli.load_settings()
        source = cli.database_path(settings.data_directory)
        if destination is None:
            root = root or settings.storage.backup_directory
            environment = os.environ.get("REEFPROOF_ENVIRONMENT", "development").casefold()
            if root is None and environment == "production":
                root = Path("/backup")
            if root is None:
                typer.echo(
                    json.dumps(
                        {
                            "error": (
                                "configure storage.backup_directory or REEFPROOF_BACKUP_DIRECTORY"
                            ),
                            "status": "FAIL",
                        },
                        sort_keys=True,
                    )
                )
                raise typer.Exit(code=2)
            now = datetime.now(ZoneInfo(settings.timezone))
            destination = (
                root / now.strftime("%Y-%m-%d") / f"reefproof-{now.strftime('%H%M%S%f')}.sqlite3"
            )
        if not source.is_file():
            typer.echo(
                json.dumps({"database": str(source), "status": "UNINITIALIZED"}, sort_keys=True)
            )
            raise typer.Exit(code=2)
        try:
            database = cli.Database(source)
            database.backup_to(destination)
            backup = cli.Database(destination)
            latest = backup.latest_return_flow_policy_revision()
            document = {
                "destination": str(destination.resolve()),
                "integrity": backup.integrity_check(),
                "latest_rule_revision": (
                    None if latest is None else latest.model_dump(mode="json")
                ),
                "schema_version": backup.schema_version(),
                "source": str(source),
                "status": "PASS",
            }
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(
                json.dumps(
                    {
                        "destination": str(destination),
                        "error": str(error),
                        "source": str(source),
                        "status": "FAIL",
                    },
                    sort_keys=True,
                )
            )
            raise typer.Exit(code=2) from error
        typer.echo(json.dumps(document, sort_keys=True))

    @database_app.command("restore")
    def storage_restore(
        source: Annotated[Path, typer.Argument(help="Existing SQLite backup path.")],
        destination: Annotated[
            Path,
            typer.Argument(help="New restore target; existing files are never overwritten."),
        ],
    ) -> None:
        """Restore a verified backup to a new target without overwriting existing files."""

        import reefproof.cli as cli

        try:
            restored = cli.Database.restore_to(source, destination)
            latest = restored.latest_return_flow_policy_revision()
            document = {
                "destination": str(destination.resolve()),
                "integrity": restored.integrity_check(),
                "latest_rule_revision": (
                    None if latest is None else latest.model_dump(mode="json")
                ),
                "schema_version": restored.schema_version(),
                "source": str(source.resolve()),
                "status": "PASS",
            }
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(
                json.dumps(
                    {
                        "destination": str(destination),
                        "error": str(error),
                        "source": str(source),
                        "status": "FAIL",
                    },
                    sort_keys=True,
                )
            )
            raise typer.Exit(code=2) from error
        typer.echo(json.dumps(document, sort_keys=True))
