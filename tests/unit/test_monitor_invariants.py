from __future__ import annotations

from datetime import datetime, timedelta

from reefproof.invariants import InvariantState
from reefproof.invariants.monitor import MonitorContext, evaluate_monitor
from reefproof.invariants.registry import explain_invariant

NOW = datetime.fromisoformat("2026-07-25T18:00:00-04:00")
CONFIG_HASH = f"sha256:{'1' * 64}"
ANNOTATION_HASH = f"sha256:{'2' * 64}"
RUN_ID = "d2345678-1234-4234-8234-123456789abc"


def _context(**changes: object) -> MonitorContext:
    values: dict[str, object] = {
        "last_valid_configuration_at": NOW - timedelta(seconds=30),
        "configuration_hash": CONFIG_HASH,
        "annotation_hash": ANNOTATION_HASH,
        "latest_evaluated_configuration_hash": CONFIG_HASH,
        "last_evaluation_at": NOW - timedelta(seconds=20),
        "maximum_configuration_age_seconds": 600,
        "maximum_evaluation_delay_seconds": 15,
        "alert_delivery_state": "healthy",
    }
    values.update(changes)
    return MonitorContext.model_validate(values)


def _result(context: MonitorContext, invariant_id: str):
    results = evaluate_monitor(
        context,
        evaluation_timestamp=NOW,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in results if result.invariant_id == invariant_id)


def test_rp_monitor_001_passes_for_fresh_configuration() -> None:
    result = _result(_context(), "RP-MONITOR-001")

    assert result.state is InvariantState.PASS
    assert result.configuration_hash == CONFIG_HASH


def test_rp_monitor_001_fails_for_stale_configuration() -> None:
    result = _result(
        _context(last_valid_configuration_at=NOW - timedelta(seconds=601)),
        "RP-MONITOR-001",
    )

    assert result.state is InvariantState.FAIL
    assert "monitoring confidence" in result.detailed_explanation.lower()


def test_rp_monitor_001_is_unknown_before_first_observation() -> None:
    result = _result(
        _context(last_valid_configuration_at=None, configuration_hash=None),
        "RP-MONITOR-001",
    )

    assert result.state is InvariantState.UNKNOWN
    assert result.configuration_hash == "UNKNOWN"


def test_rp_monitor_002_passes_when_latest_configuration_is_evaluated() -> None:
    result = _result(_context(), "RP-MONITOR-002")

    assert result.state is InvariantState.PASS


def test_rp_monitor_002_fails_when_new_configuration_misses_deadline() -> None:
    result = _result(
        _context(
            last_valid_configuration_at=NOW - timedelta(seconds=16),
            latest_evaluated_configuration_hash=f"sha256:{'3' * 64}",
        ),
        "RP-MONITOR-002",
    )

    assert result.state is InvariantState.FAIL
    assert CONFIG_HASH in result.evidence


def test_rp_monitor_002_is_unknown_without_evaluation_evidence() -> None:
    result = _result(
        _context(
            last_valid_configuration_at=NOW - timedelta(seconds=5),
            latest_evaluated_configuration_hash=None,
            last_evaluation_at=None,
        ),
        "RP-MONITOR-002",
    )

    assert result.state is InvariantState.UNKNOWN


def test_rp_monitor_003_passes_when_delivery_is_healthy() -> None:
    result = _result(_context(), "RP-MONITOR-003")

    assert result.state is InvariantState.PASS


def test_rp_monitor_003_fails_locally_when_delivery_is_unhealthy() -> None:
    result = _result(_context(alert_delivery_state="unhealthy"), "RP-MONITOR-003")

    assert result.state is InvariantState.FAIL
    assert "local health" in result.recommended_operator_action.lower()


def test_rp_monitor_003_is_unknown_before_delivery_is_verified() -> None:
    result = _result(_context(alert_delivery_state="unverified"), "RP-MONITOR-003")

    assert result.state is InvariantState.UNKNOWN


def test_monitor_invariants_are_explainable() -> None:
    for invariant_id in ("RP-MONITOR-001", "RP-MONITOR-002", "RP-MONITOR-003"):
        explanation = explain_invariant(invariant_id)

        assert invariant_id in explanation
        assert "PASS:" in explanation
        assert "FAIL:" in explanation
        assert "UNKNOWN:" in explanation
