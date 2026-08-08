"""Fixture-backed vertical evaluation and alerting pipeline."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reefproof.alerting import AlertCoordinator, DeliveryResult, DeliveryStatus
from reefproof.configuration import (
    ConfigurationSnapshot,
    load_fixture,
    snapshot_fixture,
)
from reefproof.invariants import EvaluationRun, evaluate_graph
from reefproof.invariants.monitor import AlertDeliveryState
from reefproof.reliability import ReliabilityGraph, build_graph
from reefproof.service.state import RuntimeStateStore
from reefproof.storage import Database, FindingTransition


class PipelineRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot: ConfigurationSnapshot
    graph: ReliabilityGraph
    evaluation: EvaluationRun
    snapshot_inserted: bool
    evaluation_duration_seconds: float
    transitions: tuple[FindingTransition, ...]
    deliveries: tuple[DeliveryResult, ...]


class FixtureEvaluationPipeline:
    """One complete offline assurance loop with no network or control path."""

    def __init__(
        self,
        *,
        database: Database,
        alert_coordinators: tuple[AlertCoordinator, ...],
        runtime_state: RuntimeStateStore | None = None,
    ) -> None:
        if not alert_coordinators:
            raise ValueError("at least one alert coordinator is required")
        self._database = database
        self._alerts = alert_coordinators
        self._runtime_state = runtime_state

    async def run(
        self,
        fixture_path: Path,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
    ) -> PipelineRun:
        snapshot = snapshot_fixture(load_fixture(fixture_path))
        graph = build_graph(snapshot)
        evaluation_started = time.monotonic()
        evaluation = evaluate_graph(
            graph,
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
        )
        evaluation_duration_seconds = time.monotonic() - evaluation_started
        snapshot_inserted = self._database.record_snapshot(snapshot)
        transitions = self._database.record_evaluation(evaluation)
        if self._runtime_state is not None:
            self._runtime_state.record_evaluation(
                snapshot=snapshot,
                evaluation=evaluation,
                observed_at=evaluation_timestamp,
                evaluation_duration_seconds=evaluation_duration_seconds,
            )
        transitions_by_invariant = {
            transition.invariant_id: transition for transition in transitions
        }
        entity_names = {node.node_id: node.display_name for node in graph.nodes}

        deliveries: list[DeliveryResult] = []
        for result in evaluation.results:
            for coordinator in self._alerts:
                deliveries.append(
                    await coordinator.process(
                        result=result,
                        finding=self._database.active_finding(result.invariant_id),
                        transition=transitions_by_invariant.get(result.invariant_id),
                        entity_names=entity_names,
                        now=evaluation_timestamp,
                    )
                )
        if self._runtime_state is not None:
            if any(delivery.status is DeliveryStatus.FAILURE for delivery in deliveries):
                self._runtime_state.record_alert_delivery(AlertDeliveryState.UNHEALTHY)
            elif any(delivery.status is DeliveryStatus.SUCCESS for delivery in deliveries):
                self._runtime_state.record_alert_delivery(AlertDeliveryState.HEALTHY)
        return PipelineRun(
            snapshot=snapshot,
            graph=graph,
            evaluation=evaluation,
            snapshot_inserted=snapshot_inserted,
            evaluation_duration_seconds=evaluation_duration_seconds,
            transitions=transitions,
            deliveries=tuple(deliveries),
        )
