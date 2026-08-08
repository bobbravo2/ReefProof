"""ReefProof monitor-confidence invariants."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from reefproof.invariants.models import InvariantResult, InvariantState, Severity


class AlertDeliveryState(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNVERIFIED = "unverified"


class MonitorContext(BaseModel):
    """Runtime evidence required to assess ReefProof's own confidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    last_valid_configuration_at: datetime | None
    configuration_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    annotation_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    latest_evaluated_configuration_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    last_evaluation_at: datetime | None
    maximum_configuration_age_seconds: int = Field(gt=0)
    maximum_evaluation_delay_seconds: int = Field(gt=0)
    alert_delivery_state: AlertDeliveryState = Field(strict=False)

    @model_validator(mode="after")
    def timestamps_must_be_timezone_aware(self) -> MonitorContext:
        for name in ("last_valid_configuration_at", "last_evaluation_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must include a timezone")
        return self


class _MonitorRule:
    invariant_id: str
    version = "1"
    severity: Severity
    title: str

    def evaluate(
        self,
        context: MonitorContext,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        raise NotImplementedError

    def explain(self) -> str:
        raise NotImplementedError

    def _result(
        self,
        *,
        context: MonitorContext,
        state: InvariantState,
        summary: str,
        explanation: str,
        evidence: tuple[str, ...],
        missing: tuple[str, ...],
        action: str,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        return InvariantResult(
            invariant_id=self.invariant_id,
            version=self.version,
            severity=self.severity,
            state=state,
            summary=summary,
            detailed_explanation=explanation,
            affected_entities=(),
            evidence=evidence,
            missing_evidence=missing,
            recommended_operator_action=action,
            evaluation_timestamp=evaluation_timestamp,
            configuration_hash=context.configuration_hash or "UNKNOWN",
            annotation_hash=context.annotation_hash or "UNKNOWN",
            policy_hash=policy_hash,
            evaluation_run_id=evaluation_run_id,
        )


class ConfigurationObservationStaleRule(_MonitorRule):
    invariant_id = "RP-MONITOR-001"
    severity = Severity.CRITICAL
    title = "Configuration observation must remain fresh"

    def evaluate(
        self,
        context: MonitorContext,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        observed_at = context.last_valid_configuration_at
        if observed_at is None or context.configuration_hash is None:
            return self._result(
                context=context,
                state=InvariantState.UNKNOWN,
                summary="No valid configuration observation is available.",
                explanation=(
                    "ReefProof has not yet obtained enough evidence to assess "
                    "configuration-observation freshness."
                ),
                evidence=(),
                missing=("A valid configuration observation and hash.",),
                action=(
                    "No reef action is implied. Check local transport health if "
                    "initial observation does not complete."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        age_seconds = (evaluation_timestamp - observed_at).total_seconds()
        if age_seconds < 0:
            return self._result(
                context=context,
                state=InvariantState.UNKNOWN,
                summary="Configuration-observation time is inconsistent.",
                explanation="The last observation timestamp is in the future.",
                evidence=(observed_at.isoformat(),),
                missing=("A trustworthy wall-clock relationship.",),
                action="Check ReefProof host clock synchronization.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )
        if age_seconds > context.maximum_configuration_age_seconds:
            return self._result(
                context=context,
                state=InvariantState.FAIL,
                summary="Configuration observation is stale.",
                explanation=(
                    "Monitoring confidence is lost because the last valid configuration "
                    f"is {int(age_seconds)} seconds old."
                ),
                evidence=(observed_at.isoformat(), context.configuration_hash),
                missing=(),
                action=(
                    "No immediate reef action is implied. Inspect ReefProof transport "
                    "and HYDROS cloud connectivity locally."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )
        return self._result(
            context=context,
            state=InvariantState.PASS,
            summary="Configuration observation is fresh.",
            explanation=(
                f"The last valid configuration is {int(age_seconds)} seconds old, "
                "within the configured maximum age."
            ),
            evidence=(observed_at.isoformat(), context.configuration_hash),
            missing=(),
            action="No immediate action.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    def explain(self) -> str:
        return """RP-MONITOR-001 v1 — Configuration observation must remain fresh

Protects:
  Monitoring confidence from silently relying on an obsolete configuration.

Required evidence:
  A trustworthy configuration hash, its observation time, and the configured
  maximum observation age.

PASS:
  The latest valid configuration is within its maximum age.
FAIL:
  The latest valid configuration is older than its maximum age.
UNKNOWN:
  No trustworthy configuration observation exists yet.

This finding concerns ReefProof observation health, not proof HYDROS is unsafe."""


class PolicyEvaluationStaleRule(_MonitorRule):
    invariant_id = "RP-MONITOR-002"
    severity = Severity.CRITICAL
    title = "New configurations must be evaluated before the deadline"

    def evaluate(
        self,
        context: MonitorContext,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        observed_at = context.last_valid_configuration_at
        configuration_hash = context.configuration_hash
        if observed_at is None or configuration_hash is None:
            return self._unknown(
                context,
                evaluation_timestamp,
                evaluation_run_id,
                policy_hash,
                "A valid configuration observation and hash.",
            )

        last_evaluation_at = context.last_evaluation_at
        if (
            context.latest_evaluated_configuration_hash == configuration_hash
            and last_evaluation_at is not None
            and last_evaluation_at >= observed_at
        ):
            return self._result(
                context=context,
                state=InvariantState.PASS,
                summary="The latest configuration has been evaluated.",
                explanation="The current configuration hash has a completed evaluation.",
                evidence=(
                    configuration_hash,
                    last_evaluation_at.isoformat(),
                ),
                missing=(),
                action="No immediate action.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        delay_seconds = (evaluation_timestamp - observed_at).total_seconds()
        if delay_seconds > context.maximum_evaluation_delay_seconds:
            return self._result(
                context=context,
                state=InvariantState.FAIL,
                summary="The latest configuration evaluation is stale.",
                explanation=(
                    "A new valid configuration has remained unevaluated beyond the "
                    f"{context.maximum_evaluation_delay_seconds}-second deadline."
                ),
                evidence=(configuration_hash, observed_at.isoformat()),
                missing=(),
                action="Inspect the local evaluator and storage path; assurance is degraded.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )
        return self._unknown(
            context,
            evaluation_timestamp,
            evaluation_run_id,
            policy_hash,
            "A completed evaluation for the current configuration hash.",
        )

    def _unknown(
        self,
        context: MonitorContext,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
        missing: str,
    ) -> InvariantResult:
        return self._result(
            context=context,
            state=InvariantState.UNKNOWN,
            summary="Current policy-evaluation status is not yet known.",
            explanation=(
                "ReefProof lacks a completed evaluation for the latest valid "
                "configuration, but its evaluation deadline has not been proven missed."
            ),
            evidence=tuple(
                value
                for value in (
                    context.configuration_hash,
                    (
                        context.last_valid_configuration_at.isoformat()
                        if context.last_valid_configuration_at
                        else None
                    ),
                )
                if value is not None
            ),
            missing=(missing,),
            action="Allow the current evaluation deadline, then inspect local evaluator health.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    def explain(self) -> str:
        return """RP-MONITOR-002 v1 — New configurations need timely evaluation

Protects:
  Monitoring confidence from observing a change without evaluating its policy.

Required evidence:
  The current configuration hash and observation time, the latest completed
  evaluation hash and time, and the configured evaluation deadline.

PASS:
  The current configuration hash has a completed evaluation.
FAIL:
  A current configuration remains unevaluated beyond its deadline.
UNKNOWN:
  Evaluation evidence is pending or the current configuration is unknown.

Inspect the local evaluator; no direct reef action is implied."""


class AlertDeliveryHealthRule(_MonitorRule):
    invariant_id = "RP-MONITOR-003"
    severity = Severity.HIGH
    title = "Configured alert delivery must be locally verifiable"

    def evaluate(
        self,
        context: MonitorContext,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        if context.alert_delivery_state is AlertDeliveryState.HEALTHY:
            state = InvariantState.PASS
            summary = "Alert delivery is locally verified healthy."
            explanation = "The configured delivery adapter passed its local verification."
            missing: tuple[str, ...] = ()
            action = "No immediate action."
        elif context.alert_delivery_state is AlertDeliveryState.UNHEALTHY:
            state = InvariantState.FAIL
            summary = "Alert delivery is unhealthy."
            explanation = (
                "The configured delivery adapter failed local verification. This does "
                "not imply that HYDROS itself is unsafe."
            )
            missing = ()
            action = "Inspect ReefProof local health and logs; do not rely on this adapter."
        else:
            state = InvariantState.UNKNOWN
            summary = "Alert delivery has not been verified."
            explanation = "No successful or failed local delivery verification exists yet."
            missing = ("A local alert-delivery verification result.",)
            action = "Run or await local adapter verification."
        return self._result(
            context=context,
            state=state,
            summary=summary,
            explanation=explanation,
            evidence=(f"alert_delivery_state={context.alert_delivery_state.value}",),
            missing=missing,
            action=action,
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    def explain(self) -> str:
        return """RP-MONITOR-003 v1 — Alert delivery must be locally verifiable

Protects:
  Human notification confidence when the configured alert path fails.

Required evidence:
  A local verification result for every configured alert-delivery adapter.

PASS:
  Local adapter verification succeeded.
FAIL:
  Local adapter verification failed.
UNKNOWN:
  Delivery has not yet been verified.

Inspect local health and logs; Home Assistant is not used to report its own failure."""


MONITOR_RULES: tuple[_MonitorRule, ...] = (
    ConfigurationObservationStaleRule(),
    PolicyEvaluationStaleRule(),
    AlertDeliveryHealthRule(),
)


def evaluate_monitor(
    context: MonitorContext,
    *,
    evaluation_timestamp: datetime,
    evaluation_run_id: str,
) -> tuple[InvariantResult, ...]:
    """Evaluate ReefProof health independently from the reliability graph."""

    if evaluation_timestamp.tzinfo is None or evaluation_timestamp.utcoffset() is None:
        raise ValueError("evaluation_timestamp must include a timezone")
    policy_document = [
        {
            "invariant_id": rule.invariant_id,
            "version": rule.version,
            "severity": rule.severity.value,
        }
        for rule in MONITOR_RULES
    ]
    encoded = json.dumps(
        policy_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    policy_hash = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return tuple(
        rule.evaluate(
            context,
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )
        for rule in MONITOR_RULES
    )
