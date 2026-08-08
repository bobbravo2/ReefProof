"""Runtime and daemon CLI commands."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Annotated

import typer

from reefproof.service.lifecycle import DEFAULT_STOP_TIMEOUT_SECONDS, DaemonState
from reefproof.service.workbench import EndpointState, observe_workbench


class WorkbenchConflict(RuntimeError):
    """A healthy or foreign process owns the configured interface."""


def register(app: typer.Typer, daemon_app: typer.Typer) -> None:
    def start_verified(cli, lifecycle, project_id: str | None):
        settings = cli._serve_settings(bind=None, port=None, project_id=project_id)
        before = observe_workbench(settings, lifecycle)
        if before.endpoint is EndpointState.REEFPROOF:
            if before.managed:
                return before.daemon, False
            raise WorkbenchConflict(
                "Workbench is already running outside this daemon; refusing to claim it"
            )
        if before.endpoint is EndpointState.FOREIGN:
            raise WorkbenchConflict(
                f"configured interface is occupied by a non-ReefProof listener: {before.status_url}"
            )
        status = lifecycle.start(cli._daemon_command(project_id))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observed = observe_workbench(settings, lifecycle, timeout=0.2)
            if observed.endpoint is EndpointState.REEFPROOF and observed.managed:
                return status, True
            if lifecycle.status().state is not DaemonState.RUNNING:
                break
            time.sleep(0.1)
        with contextlib.suppress(cli.LifecycleError):
            lifecycle.stop(timeout_seconds=DEFAULT_STOP_TIMEOUT_SECONDS)
        raise cli.LifecycleError(
            f"daemon did not expose a valid ReefProof status endpoint; inspect {lifecycle.log_file}"
        )

    @app.command()
    def serve(
        bind: Annotated[
            str | None,
            typer.Option(
                "--bind",
                help=(
                    "Override the API bind address. Non-loopback values are an explicit "
                    "opt-in for container serving."
                ),
            ),
        ] = None,
        port: Annotated[
            int | None,
            typer.Option("--port", min=1, max=65535, help="Override the API port."),
        ] = None,
        project_id: Annotated[
            str | None,
            typer.Option(
                "--project-id",
                help="Override the active project ID for this serve process.",
            ),
        ] = None,
        open_browser: Annotated[
            bool,
            typer.Option(
                "--open/--no-open",
                help="Open the local Mock Collective workbench in the default browser.",
            ),
        ] = True,
        reload: Annotated[
            bool | None,
            typer.Option(
                "--reload/--no-reload",
                help="Restart on local file changes in development (always off in production).",
            ),
        ] = None,
    ) -> None:
        """Serve the loopback-only local assurance workbench in the foreground by default.

        In development, source and authored configuration changes request a graceful
        restart unless ``--no-reload`` is supplied. Use ``reefproof daemon`` when a
        detached process with a PID file is needed. Local defaults remain loopback;
        use an explicit bind override for a supervised container.
        """

        import reefproof.cli as cli

        environment = os.environ.get("REEFPROOF_ENVIRONMENT", "development").lower()
        if environment not in {"development", "production"}:
            typer.echo(
                "FAIL: REEFPROOF_ENVIRONMENT must be development or production",
                err=True,
            )
            raise typer.Exit(code=2)
        reload_enabled = environment == "development" and reload is not False

        try:
            runtime = cli.build_runtime(cli._serve_settings(bind, port, project_id))
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(f"FAIL: could not start local workbench — {error}", err=True)
            raise typer.Exit(code=2) from error

        host = runtime.settings.api.bind
        browser_host = f"[{host}]" if ":" in host else host
        workbench_url = f"http://{browser_host}:{runtime.settings.api.port}/workbench"
        typer.echo(f"ReefProof local workbench: {workbench_url}")
        typer.echo("Evidence provenance: MANUAL / NOT LIVE")
        typer.echo("Operator runtime settings:")
        typer.echo(f"  environment={environment}")
        typer.echo(f"  bind={runtime.settings.api.bind}")
        typer.echo(f"  port={runtime.settings.api.port}")
        typer.echo(f"  data_directory={runtime.settings.data_directory}")
        typer.echo(f"  active_project_id={runtime.settings.project.project_id}")
        typer.echo(f"  log_level={runtime.settings.log_level}")
        typer.echo(f"  json_logs={'enabled' if runtime.settings.json_logs else 'disabled'}")
        typer.echo(f"  stdout_color={'enabled' if cli._stdout_supports_color() else 'disabled'}")
        typer.echo(f"  reload_watcher={'enabled' if reload_enabled else 'disabled'}")
        typer.echo(
            "  bootstrap_secret="
            + (
                "configured"
                if os.environ.get("REEFPROOF_BOOTSTRAP_SECRET")
                else "generated-per-start"
            )
        )
        typer.echo('Access log format: <level> <client> - "<request>" <status>')
        typer.echo("Press Ctrl-C to stop.")

        def open_workbench() -> None:
            if not cli.webbrowser.open(workbench_url):
                typer.echo(f"WARNING: could not open the default browser; visit {workbench_url}")

        try:
            cli.run_api(
                runtime,
                on_started=open_workbench if open_browser else None,
                reload=reload_enabled,
                runtime_factory=lambda: cli.build_runtime(
                    cli._serve_settings(bind, port, project_id)
                ),
            )
        except KeyboardInterrupt:
            typer.echo("Stopped ReefProof local workbench.")

    @daemon_app.command("start")
    def daemon_start(
        pid_file: Annotated[
            Path | None,
            typer.Option(
                "--pid-file",
                help=(
                    "PID file to create; defaults to a project-scoped file under "
                    "REEFPROOF_DATA_DIRECTORY."
                ),
            ),
        ] = None,
        log_file: Annotated[
            Path | None,
            typer.Option(
                "--log-file",
                help=(
                    "Detached daemon log file; defaults to "
                    "REEFPROOF_DATA_DIRECTORY/reefproof-daemon.log."
                ),
            ),
        ] = None,
        project_id: Annotated[
            str | None,
            typer.Option(
                "--project-id",
                help="Project ID used for daemon runtime and default PID/log file names.",
            ),
        ] = None,
    ) -> None:
        """Start one detached ``serve --no-open`` process and record its PID."""

        import reefproof.cli as cli

        try:
            lifecycle = cli._daemon_lifecycle(
                pid_file=pid_file,
                log_file=log_file,
                project_id=project_id,
            )
            status, started = start_verified(cli, lifecycle, project_id)
        except WorkbenchConflict as error:
            typer.echo(f"FAIL: {error}", err=True)
            raise typer.Exit(code=1) from error
        except (cli.LifecycleError, OSError, ValueError) as error:
            typer.echo(f"FAIL: {error}", err=True)
            raise typer.Exit(code=2) from error
        if started:
            typer.echo(f"Started ReefProof daemon (PID {status.pid}).")
        else:
            typer.echo(f"ReefProof daemon is already running (PID {status.pid}).")
        typer.echo(f"PID file: {lifecycle.pid_file}")
        typer.echo(f"Log file: {lifecycle.log_file}")

    @daemon_app.command("stop")
    def daemon_stop(
        pid_file: Annotated[
            Path | None,
            typer.Option(
                "--pid-file",
                help=(
                    "PID file to stop; defaults to a project-scoped file under "
                    "REEFPROOF_DATA_DIRECTORY."
                ),
            ),
        ] = None,
        timeout_seconds: Annotated[
            float,
            typer.Option(
                "--timeout",
                min=0.0,
                help="Seconds to wait for graceful shutdown before reporting a timeout.",
            ),
        ] = DEFAULT_STOP_TIMEOUT_SECONDS,
        project_id: Annotated[
            str | None,
            typer.Option(
                "--project-id",
                help="Project ID used to resolve the default daemon PID file.",
            ),
        ] = None,
    ) -> None:
        """Request graceful shutdown of the PID-file daemon; stopping is idempotent."""

        import reefproof.cli as cli

        try:
            lifecycle = cli._daemon_lifecycle(pid_file=pid_file, project_id=project_id)
            status = lifecycle.stop(timeout_seconds=timeout_seconds)
        except (cli.LifecycleError, OSError, ValueError) as error:
            typer.echo(f"FAIL: {error}", err=True)
            raise typer.Exit(code=2) from error
        if status.state is DaemonState.STOPPED:
            typer.echo(f"ReefProof daemon stopped. PID file: {lifecycle.pid_file}")
        else:
            typer.echo(f"ReefProof daemon state: {status.state.value} (PID {status.pid}).")

    @daemon_app.command("restart")
    def daemon_restart(
        project_id: Annotated[
            str | None,
            typer.Option(
                "--project-id",
                help="Project ID used to resolve the managed daemon.",
            ),
        ] = None,
    ) -> None:
        """Restart only a running PID-file-owned daemon and verify its endpoint."""

        import reefproof.cli as cli

        lifecycle = cli._daemon_lifecycle(pid_file=None, project_id=project_id)
        if lifecycle.status().state is not DaemonState.RUNNING:
            typer.echo("FAIL: no running managed daemon to restart", err=True)
            raise typer.Exit(code=1)
        try:
            lifecycle.stop(timeout_seconds=DEFAULT_STOP_TIMEOUT_SECONDS)
            status, _ = start_verified(cli, lifecycle, project_id)
        except (cli.LifecycleError, OSError, ValueError) as error:
            typer.echo(f"FAIL: {error}", err=True)
            raise typer.Exit(code=2) from error
        typer.echo(f"Restarted ReefProof daemon (PID {status.pid}).")

    @daemon_app.command("status")
    def daemon_status(
        pid_file: Annotated[
            Path | None,
            typer.Option(
                "--pid-file",
                help=(
                    "PID file to inspect; defaults to a project-scoped file under "
                    "REEFPROOF_DATA_DIRECTORY."
                ),
            ),
        ] = None,
        project_id: Annotated[
            str | None,
            typer.Option(
                "--project-id",
                help="Project ID used to resolve the default daemon PID file.",
            ),
        ] = None,
    ) -> None:
        """Report whether the configured PID is running, stopped, stale, or invalid."""

        import reefproof.cli as cli

        try:
            lifecycle = cli._daemon_lifecycle(pid_file=pid_file, project_id=project_id)
            status = lifecycle.status()
        except (cli.LifecycleError, OSError, ValueError) as error:
            typer.echo(f"FAIL: {error}", err=True)
            raise typer.Exit(code=2) from error
        if status.state is DaemonState.RUNNING:
            typer.echo(f"ReefProof daemon is running (PID {status.pid}).")
            return
        if status.state is DaemonState.STOPPED:
            typer.echo(f"ReefProof daemon is stopped. PID file: {lifecycle.pid_file}")
            raise typer.Exit(code=1)
        if status.state is DaemonState.STALE:
            typer.echo(f"ReefProof daemon PID file is stale (PID {status.pid}).", err=True)
        else:
            typer.echo(f"FAIL: {status.detail or 'invalid PID file'}", err=True)
        raise typer.Exit(code=2)
