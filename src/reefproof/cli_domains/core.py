"""Core CLI commands: version, doctor, and status."""

from __future__ import annotations

import platform
from typing import Annotated

import typer

from reefproof.service.workbench import EndpointState, observe_workbench


def register(app: typer.Typer) -> None:
    @app.command()
    def version() -> None:
        """Show package, Python, source, and build identity."""

        import reefproof.cli as cli

        packaged = cli.BUILD_REVISION != "UNKNOWN"
        commit = cli.BUILD_REVISION if packaged else cli._development_git_commit()
        state = "packaged" if packaged else ("development" if commit else "unknown")
        typer.echo(f"ReefProof {cli.__version__}")
        typer.echo(f"Python {platform.python_version()}")
        typer.echo(f"Git commit: {commit or 'UNKNOWN'}")
        typer.echo(f"Build state: {state}")
        typer.echo(f"Build source: {cli.BUILD_SOURCE}")
        typer.echo(f"Build created: {cli.BUILD_CREATED}")

    @app.command()
    def doctor() -> None:
        """Check local development health without network access or device mutation."""

        import reefproof.cli as cli

        checks = cli.run_checks()
        for check in checks:
            typer.echo(f"{check.status}: {check.name} — {check.detail}")
        failures = sum(check.status == "FAIL" for check in checks)
        warnings = sum(check.status == "WARN" for check in checks)
        typer.echo(f"Doctor result: {failures} failure(s), {warnings} warning(s)")
        if failures:
            raise typer.Exit(code=1)

    @app.command("status")
    def workbench_status(
        require_ready: Annotated[
            bool,
            typer.Option(
                "--require-ready",
                help="Exit nonzero unless the reachable Workbench reports assurance readiness.",
            ),
        ] = False,
    ) -> None:
        """Check whether the configured ReefProof workbench is reachable."""

        import reefproof.cli as cli

        settings = cli.load_settings(create_data_directory=False)
        lifecycle = cli._daemon_lifecycle(pid_file=None)
        observation = observe_workbench(settings, lifecycle)
        if observation.endpoint is EndpointState.STOPPED:
            typer.echo("FAIL: ReefProof workbench is not reachable")
            typer.echo(f"URL: {observation.workbench_url}")
            typer.echo(f"Configured mode: {settings.mode}")
            typer.echo("Start: ./reefproof serve --no-open")
            raise typer.Exit(code=1)
        if observation.endpoint is EndpointState.FOREIGN:
            typer.echo("FAIL: endpoint did not return ReefProof status")
            typer.echo(f"URL: {observation.workbench_url}")
            typer.echo(f"Configured mode: {settings.mode}")
            raise typer.Exit(code=1)

        runtime = observation.runtime
        assert runtime is not None
        typer.echo("PASS: ReefProof workbench is reachable")
        typer.echo(f"URL: {observation.workbench_url}")
        typer.echo(f"Process ownership: {'MANAGED' if observation.managed else 'UNMANAGED'}")
        typer.echo(f"Observed mode: {runtime.operating_mode}")
        typer.echo(f"Assurance readiness: {runtime.readiness.upper()}")
        typer.echo(f"Monitoring confidence: {runtime.monitoring_confidence.upper()}")
        if require_ready and runtime.readiness != "ready":
            raise typer.Exit(code=1)
