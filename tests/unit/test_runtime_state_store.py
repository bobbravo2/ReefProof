from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from reefproof.configuration import load_fixture, snapshot_fixture
from reefproof.invariants import evaluate_graph
from reefproof.invariants.monitor import AlertDeliveryState
from reefproof.reliability import build_graph
from reefproof.service import RuntimeStateStore
from reefproof.settings import Settings

NOW = datetime.fromisoformat("2026-07-25T23:30:00-04:00")


def _snapshot_and_evaluation(run_id: str):
    snapshot = snapshot_fixture(
        load_fixture(Path("tests/fixtures/configuration/unsafe-correlated-returns.json"))
    )
    evaluation = evaluate_graph(
        build_graph(snapshot),
        evaluation_timestamp=NOW,
        evaluation_run_id=run_id,
    )
    return snapshot, evaluation


def test_runtime_state_starts_without_fabricated_observation() -> None:
    store = RuntimeStateStore.from_settings(Settings(), started_at=NOW)

    state = store.snapshot()

    assert state.operating_mode == "fixture"
    assert state.configuration_hash is None
    assert state.last_valid_configuration_at is None
    assert state.hydros_connection.value == "disabled"


def test_successful_evaluation_updates_hashes_and_change_time_once() -> None:
    store = RuntimeStateStore.from_settings(Settings(), started_at=NOW)
    snapshot, evaluation = _snapshot_and_evaluation("72345678-abcd-4234-8234-123456789abc")

    store.record_evaluation(
        snapshot=snapshot,
        evaluation=evaluation,
        observed_at=NOW,
    )
    first = store.snapshot()
    store.record_evaluation(
        snapshot=snapshot,
        evaluation=evaluation.model_copy(
            update={"evaluation_run_id": "82345678-abcd-4234-8234-123456789abc"}
        ),
        observed_at=NOW + timedelta(seconds=30),
    )
    repeated = store.snapshot()

    assert first.configuration_hash == snapshot.configuration_hash
    assert first.latest_evaluated_configuration_hash == snapshot.configuration_hash
    assert first.last_configuration_change_at == NOW
    assert repeated.last_valid_configuration_at == NOW + timedelta(seconds=30)
    assert repeated.last_configuration_change_at == NOW


def test_delivery_and_storage_health_are_mutable_without_exposing_state_mutation() -> None:
    store = RuntimeStateStore.from_settings(Settings(), started_at=NOW)

    store.record_alert_delivery(AlertDeliveryState.UNHEALTHY)
    store.record_storage_writable(False)

    state = store.snapshot()
    assert state.alert_delivery_state is AlertDeliveryState.UNHEALTHY
    assert state.storage_writable is False
