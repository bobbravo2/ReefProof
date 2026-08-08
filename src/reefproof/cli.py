"""Contributor-facing ReefProof CLI."""

# Command-domain callbacks resolve compatibility bindings from this module at runtime.
# ruff: noqa: F401

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import typer

from reefproof import __version__
from reefproof._build_identity import BUILD_CREATED, BUILD_REVISION, BUILD_SOURCE
from reefproof.cli_domains import auth as auth_commands
from reefproof.cli_domains import core as core_commands
from reefproof.cli_domains import database as database_commands
from reefproof.cli_domains import evaluation as evaluation_commands
from reefproof.cli_domains import runtime as runtime_commands
from reefproof.settings import ApiSettings, Settings, load_settings

if TYPE_CHECKING:
    from reefproof.api.sessions import ActiveSession, OperatorSessions
    from reefproof.service.lifecycle import DaemonLifecycle

_LAZY_BINDINGS = {
    "ActiveSession": ("reefproof.api.sessions", "ActiveSession"),
    "OperatorSessions": ("reefproof.api.sessions", "OperatorSessions"),
    "TotpState": ("reefproof.auth_totp", "TotpState"),
    "load_fixture": ("reefproof.configuration", "load_fixture"),
    "render_snapshot": ("reefproof.configuration", "render_snapshot"),
    "snapshot_fixture": ("reefproof.configuration", "snapshot_fixture"),
    "snapshot_hydros_export": ("reefproof.configuration", "snapshot_hydros_export"),
    "write_snapshot": ("reefproof.configuration", "write_snapshot"),
    "run_checks": ("reefproof.doctor", "run_checks"),
    "Severity": ("reefproof.invariants", "Severity"),
    "evaluate_graph": ("reefproof.invariants", "evaluate_graph"),
    "explain_invariant": ("reefproof.invariants", "explain_invariant"),
    "result_exit_code": ("reefproof.invariants", "result_exit_code"),
    "build_graph": ("reefproof.reliability", "build_graph"),
    "dependency_cycles": ("reefproof.reliability", "dependency_cycles"),
    "find_correlated_redundancy": ("reefproof.reliability", "find_correlated_redundancy"),
    "render_graph": ("reefproof.reliability", "render_graph"),
    "summarize_graph": ("reefproof.reliability", "summarize_graph"),
    "import_hydros_export": ("reefproof.service.hydros_import", "import_hydros_export"),
    "DATABASE_FILENAME": ("reefproof.service.infra_smoke", "DATABASE_FILENAME"),
    "database_path": ("reefproof.service.infra_smoke", "database_path"),
    "run_infra_smoke": ("reefproof.service.infra_smoke", "run_infra_smoke"),
    "DEFAULT_STOP_TIMEOUT_SECONDS": (
        "reefproof.service.lifecycle",
        "DEFAULT_STOP_TIMEOUT_SECONDS",
    ),
    "DaemonLifecycle": ("reefproof.service.lifecycle", "DaemonLifecycle"),
    "DaemonState": ("reefproof.service.lifecycle", "DaemonState"),
    "LifecycleError": ("reefproof.service.lifecycle", "LifecycleError"),
    "build_runtime": ("reefproof.service.runtime", "build_runtime"),
    "run_api": ("reefproof.service.runtime", "run_api"),
    "Database": ("reefproof.storage", "Database"),
}


def __getattr__(name: str):
    """Load command implementation seams only when a callback needs them."""

    binding = _LAZY_BINDINGS.get(name)
    if binding is None:
        raise AttributeError(name)
    module_name, attribute_name = binding
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def _resolve(name: str):
    """Resolve a lazy binding while preserving explicit test/application overrides."""

    return globals().get(name) or __getattr__(name)


HISTORY_FILENAME = "reefproof-cli-history.log"


def _help_markup_mode() -> Literal["rich"] | None:
    """Use terminal decoration only when stdout can render it intentionally."""

    if (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    ):
        return "rich"
    return None


HELP_MARKUP_MODE = _help_markup_mode()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=HELP_MARKUP_MODE,
    help=(
        "ReefProof configuration assurance for living systems. "
        "Commands run offline by default and preserve the read-only safety boundary."
    ),
)
daemon_app = typer.Typer(
    no_args_is_help=True,
    rich_markup_mode=HELP_MARKUP_MODE,
    help=(
        "Manage the local workbench daemon with a PID file, without changing "
        "living-system configuration."
    ),
)
database_app = typer.Typer(
    no_args_is_help=True,
    rich_markup_mode=HELP_MARKUP_MODE,
    help="Inspect, back up, and restore local durable evidence storage.",
)
auth_app = typer.Typer(
    no_args_is_help=True,
    help="Manage local operator authentication.",
    rich_markup_mode=HELP_MARKUP_MODE,
)
totp_auth_app = typer.Typer(
    no_args_is_help=True,
    help="Manage the operator phone authenticator.",
    rich_markup_mode=HELP_MARKUP_MODE,
)
app.add_typer(database_app, name="database")
app.add_typer(daemon_app, name="daemon")
app.add_typer(auth_app, name="auth")
auth_app.add_typer(totp_auth_app, name="totp")


def _development_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _history_path() -> Path:
    settings = load_settings(create_data_directory=True)
    override = os.environ.get("REEFPROOF_HISTORY_FILE")
    if override:
        return Path(override).expanduser()
    return settings.data_directory / HISTORY_FILENAME


def _recent_history(limit: int = 5) -> tuple[tuple[str, str], ...]:
    path = _history_path()
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[tuple[str, str]] = []
    for line in lines[-limit:]:
        if "\t" not in line:
            continue
        timestamp, command = line.split("\t", 1)
        if command.strip():
            entries.append((timestamp, command.strip()))
    return tuple(entries)


def _record_history(arguments: tuple[str, ...]) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as history:
        history.write(f"{timestamp}\t{' '.join(arguments)}\n")


def _totp_enrollment_status() -> tuple[bool, str]:
    settings = load_settings(create_data_directory=True)
    totp_state = _resolve("TotpState")
    state = totp_state(
        settings.data_directory / "operator-totp.json",
        principal_id=settings.project.acceptance_authority_principal_id,
    )
    return state.enrolled, settings.project.project_id


def _storage_health() -> tuple[str, str]:
    path = _resolve("database_path")(load_settings().data_directory)
    if not path.is_file():
        return "UNINITIALIZED", str(path)
    try:
        integrity = _resolve("Database")(path).integrity_check()
    except (OSError, sqlite3.DatabaseError, ValueError):
        return "FAIL", str(path)
    return ("PASS" if integrity == "ok" else "FAIL"), str(path)


def _serve_settings(bind: str | None, port: int | None, project_id: str | None) -> Settings:
    settings = load_settings()
    if bind is None and port is None and project_id is None:
        return settings
    api = ApiSettings(
        allow_non_loopback=settings.api.allow_non_loopback or bind is not None,
        bind=bind or settings.api.bind,
        port=port or settings.api.port,
    )
    project = (
        settings.project
        if project_id is None
        else settings.project.model_copy(update={"project_id": project_id})
    )
    return settings.model_copy(update={"api": api, "project": project})


def _daemon_path(path: Path | None, default: Path) -> Path:
    return path.expanduser() if path is not None else default


def _daemon_command(project_id: str | None) -> tuple[str, ...]:
    project_arguments: tuple[str, ...] = ()
    if project_id is not None:
        project_arguments = ("--project-id", project_id)
    launcher = Path(sys.argv[0])
    if launcher.suffix == ".py":
        return (
            sys.executable,
            str(launcher),
            "serve",
            "--no-open",
            "--no-reload",
            *project_arguments,
        )
    return (str(launcher), "serve", "--no-open", "--no-reload", *project_arguments)


def _project_daemon_basename(project_id: str | None) -> str:
    if project_id is None:
        return "reefproof"
    return f"reefproof-{project_id}"


def _daemon_lifecycle(
    *,
    pid_file: Path | None,
    log_file: Path | None = None,
    project_id: str | None = None,
) -> DaemonLifecycle:
    settings = _serve_settings(bind=None, port=None, project_id=project_id)
    basename = _project_daemon_basename(project_id)
    default_pid_file = settings.data_directory / f"{basename}.pid"
    selected_pid_file = _daemon_path(pid_file, default_pid_file)
    default_log_file = settings.data_directory / f"{basename}-daemon.log"
    selected_log_file = _daemon_path(log_file, default_log_file)
    return _resolve("DaemonLifecycle")(
        pid_file=selected_pid_file,
        log_file=selected_log_file,
    )


def _session_operator() -> OperatorSessions:
    settings = load_settings(create_data_directory=True)
    database = _resolve("Database")(settings.data_directory / "reefproof.sqlite3")
    database.migrate()

    class _CliOperatorSessionStore:
        def record_session(
            self,
            session_id: str,
            principal_id: str,
            issued_at: int,
            authentication_generation: int,
        ) -> None:
            database.record_operator_session(
                project_id=settings.project.project_id,
                session_id=session_id,
                principal_id=principal_id,
                issued_at=issued_at,
                authentication_generation=authentication_generation,
            )

        def has_session(
            self,
            session_id: str,
            principal_id: str,
            authentication_generation: int,
        ) -> bool:
            return database.operator_session_exists(
                project_id=settings.project.project_id,
                session_id=session_id,
                principal_id=principal_id,
                authentication_generation=authentication_generation,
            )

        def revoke_session(self, session_id: str) -> bool:
            return database.revoke_operator_session(
                project_id=settings.project.project_id,
                session_id=session_id,
                revoked_at=datetime.now(UTC),
            )

        def list_sessions(
            self,
            principal_id: str,
            authentication_generation: int,
        ) -> tuple[ActiveSession, ...]:
            rows = database.list_active_operator_sessions(
                project_id=settings.project.project_id,
                principal_id=principal_id,
                authentication_generation=authentication_generation,
            )
            return tuple(
                _resolve("ActiveSession")(
                    session_id=row.session_id,
                    principal_id=row.principal_id,
                    issued_at=row.issued_at,
                )
                for row in rows
            )

    return _resolve("OperatorSessions")(
        bootstrap_secret=None,
        principal_id=settings.project.acceptance_authority_principal_id,
        principal_display_name=settings.project.acceptance_authority_display_name,
        authentication_generation=lambda: 0,
        session_store=_CliOperatorSessionStore(),
    )


def _format_session_age(now_seconds: int, issued_at: int) -> str:
    age_seconds = max(0, now_seconds - issued_at)
    if age_seconds < 60:
        return f"{age_seconds}s"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m"
    return f"{age_seconds // 3600}h"


def _stdout_supports_color() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM") != "dumb"
    )


@app.command(hidden=True)
def menu() -> None:
    """Run the attached-terminal full-screen assurance console."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        typer.echo("FAIL: the interactive menu requires an attached terminal", err=True)
        raise typer.Exit(code=2)

    from reefproof.cli_domains.menu import run_menu

    raise typer.Exit(code=run_menu())


core_commands.register(app)
runtime_commands.register(app, daemon_app)
evaluation_commands.register(app)
database_commands.register(database_app)
auth_commands.register(auth_app, totp_auth_app)


if __name__ == "__main__":
    app()
