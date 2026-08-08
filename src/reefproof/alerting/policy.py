"""Deterministic alert deduplication policy."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from reefproof.invariants import InvariantResult, InvariantState, Severity
from reefproof.storage import ActiveFinding, FindingTransition, FindingTransitionKind


class AlertAction(StrEnum):
    SKIP = "skip"
    SEND_NEW = "send_new"
    SEND_REPEAT = "send_repeat"
    SEND_RECOVERY = "send_recovery"


class AlertDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action: AlertAction
    invariant_id: str
    severity: Severity
    reason: str = Field(min_length=1)


class AlertPolicy(BaseModel):
    """Pure policy; adapters and persistence remain independent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    repeat_critical_after_seconds: int = Field(gt=0)
    alert_critical_unknown: bool
    send_recovery: bool

    def decide(
        self,
        *,
        result: InvariantResult,
        finding: ActiveFinding | None,
        transition: FindingTransition | None,
        now: datetime,
    ) -> AlertDecision:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include a timezone")

        if (
            result.state is InvariantState.PASS
            and transition is not None
            and transition.kind is FindingTransitionKind.RECOVERED
        ):
            if self.send_recovery:
                return self._decision(
                    result,
                    AlertAction.SEND_RECOVERY,
                    "A prior finding recovered and recovery notifications are enabled.",
                )
            return self._decision(
                result,
                AlertAction.SKIP,
                "Recovery notifications are disabled.",
            )

        if result.severity is not Severity.CRITICAL:
            return self._decision(
                result,
                AlertAction.SKIP,
                "Only critical results are eligible for v0.1 paging.",
            )
        if result.state is InvariantState.UNKNOWN and not self.alert_critical_unknown:
            return self._decision(
                result,
                AlertAction.SKIP,
                "Critical UNKNOWN paging is disabled.",
            )
        if result.state not in {InvariantState.FAIL, InvariantState.UNKNOWN}:
            return self._decision(
                result,
                AlertAction.SKIP,
                "The result is neither an alertable finding nor a recovery transition.",
            )
        if transition is not None and transition.kind is FindingTransitionKind.OPENED:
            return self._decision(
                result,
                AlertAction.SEND_NEW,
                "A new critical finding opened.",
            )
        if finding is None:
            return self._decision(
                result,
                AlertAction.SKIP,
                "No active finding exists for repeat-alert state.",
            )
        if finding.last_alerted is None:
            return self._decision(
                result,
                AlertAction.SEND_NEW,
                "The active critical finding has not been delivered successfully.",
            )

        elapsed = (now - finding.last_alerted).total_seconds()
        if elapsed >= self.repeat_critical_after_seconds:
            return self._decision(
                result,
                AlertAction.SEND_REPEAT,
                "The unresolved critical finding reached its repeat interval.",
            )
        return self._decision(
            result,
            AlertAction.SKIP,
            "The unresolved critical finding has not reached its repeat interval.",
        )

    @staticmethod
    def _decision(
        result: InvariantResult,
        action: AlertAction,
        reason: str,
    ) -> AlertDecision:
        return AlertDecision(
            action=action,
            invariant_id=result.invariant_id,
            severity=result.severity,
            reason=reason,
        )
