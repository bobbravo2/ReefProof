"""Thread-safe runtime assurance state."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from reefproof.configuration import ConfigurationSnapshot
from reefproof.invariants import EvaluationRun
from reefproof.invariants.monitor import AlertDeliveryState
from reefproof.service.health import ConnectionState, RuntimeState
from reefproof.settings import Settings


class RuntimeStateStore:
    """Own mutable service state while exposing immutable snapshots."""

    def __init__(self, initial: RuntimeState) -> None:
        self._state = initial
        self._lock = RLock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        started_at: datetime,
    ) -> RuntimeStateStore:
        hydros_connection = (
            ConnectionState.DISCONNECTED if settings.hydros.enabled else ConnectionState.DISABLED
        )
        return cls(
            RuntimeState(
                started_at=started_at,
                operating_mode=settings.reefproof.mode,
                hydros_connection=hydros_connection,
                mqtt_connection=ConnectionState.DISABLED,
                last_valid_configuration_at=None,
                last_configuration_change_at=None,
                configuration_hash=None,
                last_evaluation_at=None,
                last_evaluation_duration_seconds=None,
                latest_evaluated_configuration_hash=None,
                policy_loaded=True,
                policy_hash=None,
                annotation_hash=None,
                storage_writable=True,
                unrecoverable_transport_failure=None,
                alert_delivery_state=AlertDeliveryState.UNVERIFIED,
                maximum_configuration_age_seconds=(settings.hydros.maximum_config_age_seconds),
            )
        )

    def snapshot(self) -> RuntimeState:
        with self._lock:
            return self._state

    def record_evaluation(
        self,
        *,
        snapshot: ConfigurationSnapshot,
        evaluation: EvaluationRun,
        observed_at: datetime,
        evaluation_duration_seconds: float | None = None,
    ) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if evaluation_duration_seconds is not None and evaluation_duration_seconds < 0:
            raise ValueError("evaluation_duration_seconds cannot be negative")
        with self._lock:
            changed_at = self._state.last_configuration_change_at
            if self._state.configuration_hash != snapshot.configuration_hash:
                changed_at = observed_at
            self._state = self._state.model_copy(
                update={
                    "last_valid_configuration_at": observed_at,
                    "last_configuration_change_at": changed_at,
                    "configuration_hash": snapshot.configuration_hash,
                    "last_evaluation_at": evaluation.evaluation_timestamp,
                    "last_evaluation_duration_seconds": evaluation_duration_seconds,
                    "latest_evaluated_configuration_hash": snapshot.configuration_hash,
                    "policy_loaded": True,
                    "policy_hash": evaluation.policy_hash,
                    "annotation_hash": snapshot.annotation_hash,
                    "unrecoverable_transport_failure": None,
                }
            )

    def record_alert_delivery(self, state: AlertDeliveryState) -> None:
        with self._lock:
            self._state = self._state.model_copy(update={"alert_delivery_state": state})

    def record_storage_writable(self, writable: bool) -> None:
        with self._lock:
            self._state = self._state.model_copy(update={"storage_writable": writable})

    def record_transport_failure(self, reason: str | None) -> None:
        with self._lock:
            self._state = self._state.model_copy(update={"unrecoverable_transport_failure": reason})
