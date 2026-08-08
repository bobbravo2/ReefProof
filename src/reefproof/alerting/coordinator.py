"""Coordinate pure alert decisions, adapters, and durable outcomes."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from reefproof.alerting.policy import AlertAction, AlertDecision, AlertPolicy
from reefproof.alerting.protocol import AlertAdapter, AlertEvent
from reefproof.invariants import InvariantResult, InvariantState
from reefproof.storage import (
    ActiveFinding,
    AlertAttempt,
    AlertAttemptResult,
    Database,
    FindingTransition,
)


class DeliveryStatus(StrEnum):
    SKIPPED = "skipped"
    SUCCESS = "success"
    FAILURE = "failure"


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    decision: AlertDecision
    adapter: str
    status: DeliveryStatus
    attempt_id: str | None


class AlertCoordinator:
    def __init__(
        self,
        *,
        database: Database,
        policy: AlertPolicy,
        adapter: AlertAdapter,
        reefproof_base_url: str,
    ) -> None:
        self._database = database
        self._policy = policy
        self._adapter = adapter
        self._base_url = reefproof_base_url.rstrip("/")

    @property
    def adapter_name(self) -> str:
        return self._adapter.name

    async def process(
        self,
        *,
        result: InvariantResult,
        finding: ActiveFinding | None,
        transition: FindingTransition | None,
        entity_names: dict[str, str],
        now: datetime,
    ) -> DeliveryResult:
        adapter_finding = finding
        if finding is not None:
            adapter_finding = finding.model_copy(
                update={
                    "last_alerted": self._database.last_successful_alert_at(
                        result.invariant_id,
                        self._adapter.name,
                    )
                }
            )
        decision = self._policy.decide(
            result=result,
            finding=adapter_finding,
            transition=transition,
            now=now,
        )
        if decision.action is AlertAction.SKIP:
            return DeliveryResult(
                decision=decision,
                adapter=self._adapter.name,
                status=DeliveryStatus.SKIPPED,
                attempt_id=None,
            )

        event = self._event(
            result=result,
            finding=finding,
            transition=transition,
            entity_names=entity_names,
            recovery=decision.action is AlertAction.SEND_RECOVERY,
            now=now,
        )
        attempt_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            await self._adapter.send(event)
        except Exception:
            duration = time.monotonic() - started
            self._database.record_alert_attempt(
                AlertAttempt(
                    attempt_id=attempt_id,
                    invariant_id=result.invariant_id,
                    adapter=self._adapter.name,
                    action=decision.action.value,
                    attempted_at=now,
                    result=AlertAttemptResult.FAILURE,
                    duration_seconds=duration,
                    error_category="alert_delivery",
                )
            )
            return DeliveryResult(
                decision=decision,
                adapter=self._adapter.name,
                status=DeliveryStatus.FAILURE,
                attempt_id=attempt_id,
            )

        duration = time.monotonic() - started
        self._database.record_alert_attempt(
            AlertAttempt(
                attempt_id=attempt_id,
                invariant_id=result.invariant_id,
                adapter=self._adapter.name,
                action=decision.action.value,
                attempted_at=now,
                result=AlertAttemptResult.SUCCESS,
                duration_seconds=duration,
                error_category=None,
            )
        )
        return DeliveryResult(
            decision=decision,
            adapter=self._adapter.name,
            status=DeliveryStatus.SUCCESS,
            attempt_id=attempt_id,
        )

    def _event(
        self,
        *,
        result: InvariantResult,
        finding: ActiveFinding | None,
        transition: FindingTransition | None,
        entity_names: dict[str, str],
        recovery: bool,
        now: datetime,
    ) -> AlertEvent:
        first_seen = (
            finding.first_seen
            if finding is not None
            else transition.first_seen
            if transition is not None
            else now
        )
        return AlertEvent(
            source="ReefProof",
            title=(
                "HYDROS reliability invariant recovered"
                if recovery
                else "HYDROS reliability invariant violated"
            ),
            severity=result.severity,
            invariant_id=result.invariant_id,
            summary=result.summary,
            first_seen=first_seen,
            configuration_hash=result.configuration_hash,
            policy_hash=result.policy_hash,
            affected_entities=tuple(
                entity_names.get(entity_id, entity_id) for entity_id in result.affected_entities
            ),
            recommended_action=result.recommended_operator_action,
            reefproof_url=f"{self._base_url}/v1/findings/{result.invariant_id}",
            recovery=recovery or result.state is InvariantState.PASS,
        )
