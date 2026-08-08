"""Framework-independent readiness and monitoring-confidence model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reefproof.invariants.monitor import AlertDeliveryState


class ConnectionState(StrEnum):
    DISABLED = "disabled"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class AssuranceReadiness(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    UNREADY = "unready"


class MonitoringConfidence(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    LOST = "lost"
    UNKNOWN = "unknown"


class RuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    started_at: datetime
    operating_mode: Literal["fixture", "one-shot", "watch"]
    hydros_connection: ConnectionState = Field(strict=False)
    mqtt_connection: ConnectionState = Field(strict=False)
    last_valid_configuration_at: datetime | None
    last_configuration_change_at: datetime | None
    configuration_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    last_evaluation_at: datetime | None
    last_evaluation_duration_seconds: float | None = Field(default=None, ge=0)
    latest_evaluated_configuration_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    policy_loaded: bool
    policy_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    annotation_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    storage_writable: bool
    unrecoverable_transport_failure: str | None
    alert_delivery_state: AlertDeliveryState = Field(strict=False)
    maximum_configuration_age_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def timestamps_must_be_timezone_aware(self) -> RuntimeState:
        for name in (
            "started_at",
            "last_valid_configuration_at",
            "last_configuration_change_at",
            "last_evaluation_at",
        ):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must include a timezone")
        return self


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    readiness: AssuranceReadiness
    monitoring_confidence: MonitoringConfidence
    reasons: tuple[str, ...]


def evaluate_readiness(state: RuntimeState, *, now: datetime) -> ReadinessReport:
    """Evaluate whether ReefProof can currently provide trustworthy assurance."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")

    reasons: list[str] = []
    observed_at = state.last_valid_configuration_at
    if observed_at is None or state.configuration_hash is None:
        reasons.append("No valid configuration has been observed.")
    else:
        age_seconds = (now - observed_at).total_seconds()
        if age_seconds < 0:
            reasons.append("The latest configuration timestamp is in the future.")
        elif age_seconds > state.maximum_configuration_age_seconds:
            reasons.append("The latest valid configuration is stale.")

    if (
        state.configuration_hash is None
        or state.last_evaluation_at is None
        or state.latest_evaluated_configuration_hash != state.configuration_hash
    ):
        reasons.append("The latest configuration has not been evaluated.")
    if not state.policy_loaded or state.policy_hash is None:
        reasons.append("Invariant policy is not loaded successfully.")
    if not state.storage_writable:
        reasons.append("Durable storage is not writable.")
    if state.unrecoverable_transport_failure is not None:
        reasons.append(
            f"Transport has an unrecoverable failure: {state.unrecoverable_transport_failure}."
        )

    if reasons:
        confidence = (
            MonitoringConfidence.UNKNOWN
            if observed_at is None or state.configuration_hash is None
            else MonitoringConfidence.LOST
        )
        return ReadinessReport(
            readiness=AssuranceReadiness.UNREADY,
            monitoring_confidence=confidence,
            reasons=tuple(reasons),
        )

    if state.alert_delivery_state is not AlertDeliveryState.HEALTHY:
        reason = (
            "Alert delivery is unhealthy."
            if state.alert_delivery_state is AlertDeliveryState.UNHEALTHY
            else "Alert delivery has not been verified."
        )
        return ReadinessReport(
            readiness=AssuranceReadiness.DEGRADED,
            monitoring_confidence=MonitoringConfidence.DEGRADED,
            reasons=(reason,),
        )

    return ReadinessReport(
        readiness=AssuranceReadiness.READY,
        monitoring_confidence=MonitoringConfidence.HEALTHY,
        reasons=(),
    )
