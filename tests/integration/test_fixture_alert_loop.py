from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

from reefproof.alerting import (
    AlertCoordinator,
    AlertPolicy,
    ConsoleAlertAdapter,
    DeliveryStatus,
)
from reefproof.service import FixtureEvaluationPipeline, RuntimeStateStore, evaluate_readiness
from reefproof.settings import Settings
from reefproof.storage import Database

UNSAFE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
SAFE = Path("tests/fixtures/configuration/safe-independent-returns.json")
NOW = datetime.fromisoformat("2026-07-25T21:00:00-04:00")


class _FailingAdapter:
    name = "home_assistant"

    async def send(self, event: object) -> None:
        raise RuntimeError("synthetic Home Assistant outage")


def test_safe_unsafe_repeat_recovery_alert_loop(tmp_path: Path) -> None:
    stream = io.StringIO()
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    coordinator = AlertCoordinator(
        database=database,
        policy=AlertPolicy(
            repeat_critical_after_seconds=3600,
            alert_critical_unknown=False,
            send_recovery=True,
        ),
        adapter=ConsoleAlertAdapter(stream),
        reefproof_base_url="http://reefproof.local",
    )
    runtime_state = RuntimeStateStore.from_settings(Settings(), started_at=NOW)
    pipeline = FixtureEvaluationPipeline(
        database=database,
        alert_coordinators=(coordinator,),
        runtime_state=runtime_state,
    )

    unsafe = asyncio.run(
        pipeline.run(
            UNSAFE,
            evaluation_timestamp=NOW,
            evaluation_run_id="32345678-abcd-4234-8234-123456789abc",
        )
    )
    repeated = asyncio.run(
        pipeline.run(
            UNSAFE,
            evaluation_timestamp=NOW + timedelta(seconds=30),
            evaluation_run_id="42345678-abcd-4234-8234-123456789abc",
        )
    )
    recovered = asyncio.run(
        pipeline.run(
            SAFE,
            evaluation_timestamp=NOW + timedelta(seconds=60),
            evaluation_run_id="52345678-abcd-4234-8234-123456789abc",
        )
    )

    unsafe_deliveries = [
        delivery for delivery in unsafe.deliveries if delivery.status is DeliveryStatus.SUCCESS
    ]
    repeated_deliveries = [
        delivery for delivery in repeated.deliveries if delivery.status is DeliveryStatus.SUCCESS
    ]
    recovery_deliveries = [
        delivery for delivery in recovered.deliveries if delivery.status is DeliveryStatus.SUCCESS
    ]
    events = [json.loads(line) for line in stream.getvalue().splitlines()]

    assert len(unsafe_deliveries) == 1
    assert repeated_deliveries == []
    assert len(recovery_deliveries) == 1
    assert [event["recovery"] for event in events] == [False, True]
    assert all(event["invariant_id"] == "RP-CIRC-001" for event in events)
    assert database.snapshot_count() == 2
    assert database.transition_count("RP-CIRC-001") == 2
    assert database.alert_attempt_count("RP-CIRC-001") == 2
    assert database.active_finding("RP-CIRC-001") is None
    assert unsafe.evaluation_duration_seconds >= 0
    state = runtime_state.snapshot()
    assert state.configuration_hash == recovered.snapshot.configuration_hash
    assert state.last_evaluation_duration_seconds == recovered.evaluation_duration_seconds
    assert (
        evaluate_readiness(
            state,
            now=NOW + timedelta(seconds=60),
        ).readiness.value
        == "ready"
    )


def test_multi_adapter_failure_is_degraded_and_only_failed_path_retries(
    tmp_path: Path,
) -> None:
    stream = io.StringIO()
    database = Database(tmp_path / "reefproof.sqlite3")
    database.migrate()
    policy = AlertPolicy(
        repeat_critical_after_seconds=3600,
        alert_critical_unknown=False,
        send_recovery=True,
    )
    coordinators = (
        AlertCoordinator(
            database=database,
            policy=policy,
            adapter=ConsoleAlertAdapter(stream),
            reefproof_base_url="http://reefproof.local",
        ),
        AlertCoordinator(
            database=database,
            policy=policy,
            adapter=_FailingAdapter(),
            reefproof_base_url="http://reefproof.local",
        ),
    )
    runtime_state = RuntimeStateStore.from_settings(Settings(), started_at=NOW)
    pipeline = FixtureEvaluationPipeline(
        database=database,
        alert_coordinators=coordinators,
        runtime_state=runtime_state,
    )

    first = asyncio.run(
        pipeline.run(
            UNSAFE,
            evaluation_timestamp=NOW,
            evaluation_run_id="62345678-abcd-4234-8234-123456789abc",
        )
    )
    repeated = asyncio.run(
        pipeline.run(
            UNSAFE,
            evaluation_timestamp=NOW + timedelta(seconds=30),
            evaluation_run_id="72345678-abcd-4234-8234-123456789abc",
        )
    )

    circ_first = [
        delivery for delivery in first.deliveries if delivery.decision.invariant_id == "RP-CIRC-001"
    ]
    circ_repeated = [
        delivery
        for delivery in repeated.deliveries
        if delivery.decision.invariant_id == "RP-CIRC-001"
    ]
    assert [(item.adapter, item.status) for item in circ_first] == [
        ("console", DeliveryStatus.SUCCESS),
        ("home_assistant", DeliveryStatus.FAILURE),
    ]
    assert [(item.adapter, item.status) for item in circ_repeated] == [
        ("console", DeliveryStatus.SKIPPED),
        ("home_assistant", DeliveryStatus.FAILURE),
    ]
    assert len(stream.getvalue().splitlines()) == 1
    assert database.alert_attempt_count("RP-CIRC-001") == 3
    assert runtime_state.snapshot().alert_delivery_state.value == "unhealthy"
