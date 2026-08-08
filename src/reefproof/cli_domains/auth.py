"""Authentication and session management CLI commands."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer


def register(auth_app: typer.Typer, totp_auth_app: typer.Typer) -> None:
    @totp_auth_app.command("reset")
    def totp_reset(
        project: Annotated[
            str,
            typer.Option("--project", help="Configured project ID to reset."),
        ],
        confirm: Annotated[
            str,
            typer.Option(
                "--confirm",
                help="Repeat the project ID as an explicit destructive-action confirmation.",
            ),
        ],
    ) -> None:
        """Rotate authenticator state and invalidate all existing browser sessions.

        ``--confirm`` must repeat the configured project ID to prevent an
        accidental authority reset.
        """

        import reefproof.cli as cli

        settings = cli.load_settings(create_data_directory=True)
        if project != settings.project.project_id or confirm != project:
            raise typer.BadParameter("--project and --confirm must match the configured project")
        state = cli.TotpState(
            settings.data_directory / "operator-totp.json",
            principal_id=settings.project.acceptance_authority_principal_id,
        )
        state.reset()
        typer.echo(
            f"authenticator app enrollment reset for {project}; existing sessions are invalid."
        )

    @auth_app.command("sessions")
    def auth_sessions() -> None:
        """List active authenticated operator browser sessions."""

        import reefproof.cli as cli

        sessions = cli._session_operator().active_sessions()
        if not sessions:
            typer.echo("No active authenticated operator sessions.")
            return
        now_seconds = int(datetime.now(UTC).timestamp())
        typer.echo("Active authenticated operator sessions:")
        for index, session in enumerate(sessions, start=1):
            created = datetime.fromtimestamp(session.issued_at, UTC).isoformat()
            age = cli._format_session_age(now_seconds, session.issued_at)
            typer.echo(
                f"{index}. session={session.display_suffix} "
                f"principal={session.principal_id} created={created} age={age} "
                f"id={session.session_id}"
            )

    @auth_app.command("revoke-session")
    def auth_revoke_session(
        session_id: Annotated[
            str | None,
            typer.Option(
                "--session-id",
                help="Session ID to revoke directly; omit for interactive selection.",
            ),
        ] = None,
    ) -> None:
        """Revoke exactly one authenticated browser session by explicit selection."""

        import reefproof.cli as cli

        operator_sessions = cli._session_operator()
        sessions = operator_sessions.active_sessions()
        if not sessions:
            typer.echo("No active authenticated operator sessions to revoke.")
            raise typer.Exit(code=1)

        selected_session_id = session_id
        if selected_session_id is None:
            now_seconds = int(datetime.now(UTC).timestamp())
            typer.echo("Select one active session to revoke:")
            for index, session in enumerate(sessions, start=1):
                created = datetime.fromtimestamp(session.issued_at, UTC).isoformat()
                age = cli._format_session_age(now_seconds, session.issued_at)
                typer.echo(
                    f"{index}. session={session.display_suffix} "
                    f"principal={session.principal_id} created={created} age={age}"
                )
            selection = typer.prompt("Session number")
            try:
                selected_index = int(selection)
            except ValueError as error:
                raise typer.BadParameter("Session number must be an integer") from error
            if selected_index < 1 or selected_index > len(sessions):
                raise typer.BadParameter("Session number is out of range")
            selected_session_id = sessions[selected_index - 1].session_id

        known_session_ids = {session.session_id for session in sessions}
        if selected_session_id not in known_session_ids:
            raise typer.BadParameter("Session ID is not active")

        if not operator_sessions.revoke_session_id(selected_session_id):
            raise typer.BadParameter("Session ID is not active")

        typer.echo(f"Revoked operator session {selected_session_id}.")
