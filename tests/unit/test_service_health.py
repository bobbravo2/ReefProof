from __future__ import annotations

from datetime import datetime, timedelta

from reefproof.invariants.monitor import AlertDeliveryState
from reefproof.service.health import (
    AssuranceReadiness,
    MonitoringConfidence,
    RuntimeState,
    evaluate_readiness,
)

NOW = datetime.fromisoformat("2026-07-25T22:00:00-04:00")
HASH = f"sha256:{'c' * 64}"


def _state(**changes: object) -> RuntimeState:
    values: dict[str, object] = {
        "started_at": NOW - timedelta(hours=1),
        "operating_mode": "fixture",
        "hydros_connection": "disabled",
        "mqtt_connection": "disabled",
        "last_valid_configuration_at": NOW - timedelta(seconds=30),
        "last_configuration_change_at": NOW - timedelta(minutes=10),
        "configuration_hash": HASH,
        "last_evaluation_at": NOW - timedelta(seconds=20),
        "latest_evaluated_configuration_hash": HASH,
        "policy_loaded": True,
        "policy_hash": HASH,
        "annotation_hash": HASH,
        "storage_writable": True,
        "unrecoverable_transport_failure": None,
        "alert_delivery_state": "healthy",
        "maximum_configuration_age_seconds": 600,
    }
    values.update(changes)
    return RuntimeState.model_validate(values)


def test_ready_when_all_assurance_requirements_hold() -> None:
    report = evaluate_readiness(_state(), now=NOW)

    assert report.readiness is AssuranceReadiness.READY
    assert report.monitoring_confidence is MonitoringConfidence.HEALTHY
    assert report.reasons == ()


def test_stale_configuration_is_unready() -> None:
    report = evaluate_readiness(
        _state(last_valid_configuration_at=NOW - timedelta(seconds=601)),
        now=NOW,
    )

    assert report.readiness is AssuranceReadiness.UNREADY
    assert report.monitoring_confidence is MonitoringConfidence.LOST
    assert "stale" in report.reasons[0].lower()


def test_unevaluated_latest_hash_is_unready() -> None:
    report = evaluate_readiness(
        _state(latest_evaluated_configuration_hash=f"sha256:{'d' * 64}"),
        now=NOW,
    )

    assert report.readiness is AssuranceReadiness.UNREADY
    assert any("latest configuration" in reason.lower() for reason in report.reasons)


def test_policy_storage_and_transport_failures_are_unready() -> None:
    report = evaluate_readiness(
        _state(
            policy_loaded=False,
            policy_hash=None,
            storage_writable=False,
            unrecoverable_transport_failure="authorization denied",
        ),
        now=NOW,
    )

    assert report.readiness is AssuranceReadiness.UNREADY
    assert len(report.reasons) == 3


def test_alert_failure_degrades_without_making_core_assurance_unready() -> None:
    report = evaluate_readiness(
        _state(alert_delivery_state=AlertDeliveryState.UNHEALTHY),
        now=NOW,
    )

    assert report.readiness is AssuranceReadiness.DEGRADED
    assert report.monitoring_confidence is MonitoringConfidence.DEGRADED
    assert report.reasons == ("Alert delivery is unhealthy.",)


def test_startup_without_observation_is_honestly_unready() -> None:
    report = evaluate_readiness(
        _state(
            last_valid_configuration_at=None,
            configuration_hash=None,
            last_evaluation_at=None,
            latest_evaluated_configuration_hash=None,
        ),
        now=NOW,
    )

    assert report.readiness is AssuranceReadiness.UNREADY
    assert report.monitoring_confidence is MonitoringConfidence.UNKNOWN
