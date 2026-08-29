"""Snapshot, graph, invariant, and infra-smoke CLI commands."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import typer


def register(app: typer.Typer) -> None:
    @app.command("hydros-check")
    def hydros_check(
        hydros_export: Annotated[
            Path,
            typer.Option(
                "--hydros-export",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Offline HYDROS Chrome Download Config export.",
            ),
        ],
        captured_at: Annotated[
            str,
            typer.Option(help="Timezone-aware Download Config capture time."),
        ],
        output_format: Annotated[
            Literal["text", "json"],
            typer.Option("--format", help="Evaluation output format."),
        ] = "text",
        expected_temperature_unit: Annotated[
            Literal["fahrenheit"],
            typer.Option(help="Operator-confirmed expected HYDROS display unit."),
        ] = "fahrenheit",
    ) -> None:
        """Persist an offline HYDROS snapshot and confirmed unit finding."""

        import reefproof.cli as cli

        try:
            settings = cli.load_settings(create_data_directory=True)
            database = cli.Database(cli.database_path(settings.data_directory))
            database.migrate()
            now = datetime.now().astimezone()
            completed = cli.import_hydros_export(
                hydros_export,
                captured_at=datetime.fromisoformat(captured_at),
                expected_temperature_unit=expected_temperature_unit,
                database=database,
                evaluation_timestamp=now,
            )
        except (OSError, ValueError, sqlite3.DatabaseError) as error:
            raise typer.BadParameter(str(error), param_hint="--hydros-export") from error

        result = completed.evaluation.results[0]
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "detailed_explanation": result.detailed_explanation,
                        "evidence": list(result.evidence),
                        "invariant_id": result.invariant_id,
                        "severity": result.severity.value,
                        "snapshot_hash": completed.snapshot.snapshot_hash,
                        "state": result.state.value,
                        "summary": result.summary,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        typer.echo(
            f"{result.state.value} {result.severity.value.upper()} "
            f"{result.invariant_id} — {result.summary}"
        )
        typer.echo(result.detailed_explanation)
        for evidence in result.evidence:
            typer.echo(f"Evidence: {evidence}")
        typer.echo(f"Snapshot persisted: {completed.snapshot.snapshot_hash}")
        typer.echo(f"Evaluation persisted: {completed.evaluation.evaluation_run_id}")

    @app.command("snapshot")
    def snapshot(
        fixture: Annotated[
            Path | None,
            typer.Option(
                "--fixture",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Synthetic authored fixture JSON.",
            ),
        ] = None,
        hydros_export: Annotated[
            Path | None,
            typer.Option(
                "--hydros-export",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Offline HYDROS Chrome Download Config export.",
            ),
        ] = None,
        captured_at: Annotated[
            str | None,
            typer.Option(
                "--captured-at",
                help="Required timezone-aware capture time for an observed HYDROS export.",
            ),
        ] = None,
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                file_okay=True,
                dir_okay=False,
                resolve_path=True,
                help="Write canonical snapshot JSON instead of printing it.",
            ),
        ] = None,
    ) -> None:
        """Normalize offline input into deterministic snapshot evidence.

        Example: ``reefproof snapshot --fixture tests/fixtures/configuration/authored-minimal.json``
        """

        import reefproof.cli as cli

        try:
            if (fixture is None) == (hydros_export is None):
                raise ValueError("provide exactly one of --fixture or --hydros-export")
            if hydros_export is not None:
                if captured_at is None:
                    raise ValueError("--captured-at is required with --hydros-export")
                if output is not None and output == hydros_export:
                    raise ValueError("--output must not overwrite the original HYDROS export")
                parsed_captured_at = datetime.fromisoformat(captured_at)
                normalized = cli.snapshot_hydros_export(
                    hydros_export,
                    captured_at=parsed_captured_at,
                )
            else:
                assert fixture is not None
                normalized = cli.snapshot_fixture(cli.load_fixture(fixture))
            rendered = cli.render_snapshot(normalized)
            if output is None:
                typer.echo(rendered, nl=False)
            else:
                cli.write_snapshot(normalized, output)
        except (OSError, ValueError) as error:
            raise typer.BadParameter(str(error), param_hint="--fixture/--hydros-export") from error

        if output is not None:
            typer.echo(f"Wrote canonical snapshot: {output}")
            typer.echo(f"Configuration hash: {normalized.configuration_hash}")
            typer.echo(f"Annotation hash: {normalized.annotation_hash}")
            typer.echo(f"Snapshot hash: {normalized.snapshot_hash}")
            for warning in normalized.completeness_warnings:
                typer.echo(f"WARNING: {warning}")

    @app.command("graph")
    def graph_command(
        fixture: Annotated[
            Path,
            typer.Option(
                "--fixture",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Synthetic authored fixture JSON.",
            ),
        ],
        output_format: Annotated[
            Literal["text", "json"],
            typer.Option("--format", help="Graph output format."),
        ] = "text",
    ) -> None:
        """Inspect explicit reliability relationships without evaluating safety policy."""

        import reefproof.cli as cli

        try:
            graph = cli.build_graph(cli.snapshot_fixture(cli.load_fixture(fixture)))
        except (OSError, ValueError) as error:
            raise typer.BadParameter(str(error), param_hint="--fixture") from error

        if output_format == "json":
            typer.echo(cli.render_graph(graph), nl=False)
            return

        names = {node.node_id: node.display_name for node in graph.nodes}
        typer.echo(cli.summarize_graph(graph))
        correlations = cli.find_correlated_redundancy(graph)
        if correlations:
            for correlation in correlations:
                typer.echo(
                    "Correlated redundancy graph fact: "
                    f"{names[correlation.first_id]} and {names[correlation.second_id]} "
                    f"share {names[correlation.failure_domain_id]}."
                )
                typer.echo(f"Evidence: {', '.join(correlation.evidence_refs)}")
        else:
            typer.echo("No correlated redundancy graph fact is explicitly supported.")

        cycles = cli.dependency_cycles(graph)
        typer.echo(f"Dependency cycles: {len(cycles)}")
        typer.echo("This graph inspection is not an invariant safety evaluation.")

    @app.command()
    def check(
        fixture: Annotated[
            Path,
            typer.Option(
                "--fixture",
                exists=True,
                file_okay=True,
                dir_okay=False,
                readable=True,
                resolve_path=True,
                help="Synthetic authored fixture JSON.",
            ),
        ],
        output_format: Annotated[
            Literal["text", "json"],
            typer.Option("--format", help="Evaluation output format."),
        ] = "text",
        fail_on: Annotated[
            Literal["warning", "high", "critical"],
            typer.Option("--fail-on", help="Lowest severity that affects the exit code."),
        ] = "critical",
    ) -> None:
        """Evaluate registered safety invariants against an offline authored fixture."""

        import reefproof.cli as cli

        try:
            graph = cli.build_graph(cli.snapshot_fixture(cli.load_fixture(fixture)))
            run = cli.evaluate_graph(graph)
        except (OSError, ValueError) as error:
            raise typer.BadParameter(str(error), param_hint="--fixture") from error

        if output_format == "json":
            typer.echo(
                json.dumps(
                    run.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
            )
        else:
            typer.echo(f"Evaluation run: {run.evaluation_run_id}")
            typer.echo(f"Policy hash: {run.policy_hash}")
            for result in run.results:
                typer.echo(
                    f"{result.state.value} {result.severity.value.upper()} "
                    f"{result.invariant_id} — {result.summary}"
                )
                typer.echo(result.detailed_explanation)
                for missing in result.missing_evidence:
                    typer.echo(f"Missing evidence: {missing}")
                typer.echo(f"Operator action: {result.recommended_operator_action}")

        exit_code = cli.result_exit_code(run.results, fail_on=cli.Severity(fail_on))
        if exit_code:
            raise typer.Exit(code=exit_code)

    @app.command()
    def explain(
        invariant_id: Annotated[
            str,
            typer.Argument(help="Registered invariant ID, for example RP-CIRC-001."),
        ],
    ) -> None:
        """Explain one registered invariant in operator language."""

        import reefproof.cli as cli

        try:
            explanation = cli.explain_invariant(invariant_id)
        except KeyError as error:
            raise typer.BadParameter(str(error), param_hint="INVARIANT_ID") from error
        typer.echo(explanation)

    @app.command("infra-smoke")
    def infra_smoke(
        output_format: Annotated[
            Literal["json"],
            typer.Option("--format", help="Machine-readable output format."),
        ] = "json",
    ) -> None:
        """Run the bundled, network-free evidence-store scenario and print JSON."""

        import reefproof.cli as cli

        del output_format
        try:
            report = cli.run_infra_smoke(cli.load_settings().data_directory)
        except (OSError, RuntimeError, sqlite3.DatabaseError, ValueError) as error:
            typer.echo(json.dumps({"status": "FAIL", "error": str(error)}, sort_keys=True))
            raise typer.Exit(code=2) from error
        typer.echo(report.model_dump_json(indent=2))
