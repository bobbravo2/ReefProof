from __future__ import annotations

from datetime import datetime, timedelta

from reefproof.alerting import AlertAction, AlertPolicy
from reefproof.invariants import InvariantResult, InvariantState, Severity
from reefproof.storage import (
    ActiveFinding,
    FindingTransition,
    FindingTransitionKind,
)

NOW = datetime.fromisoformat("2026-07-25T20:00:00-04:00")
RUN_ID = "12345678-abcd-4234-8234-123456789abc"
HASH = f"sha256:{'a' * 64}"


def _result(
    *,
    state: InvariantState = InvariantState.FAIL,
    severity: Severity = Severity.CRITICAL,
) -> InvariantResult:
    return InvariantResult(
        invariant_id="RP-CIRC-001",
        version="1",
        severity=severity,
        state=state,
        summary="Example finding",
        detailed_explanation="Example evidence-backed explanation.",
        affected_entities=("RP.DEVICE.0123456789abcdef",),
        evidence=("RP.ANNOTATION.0123456789abcdef",),
        missing_evidence=("Missing evidence.",) if state is InvariantState.UNKNOWN else (),
        recommended_operator_action="Inspect the example.",
        evaluation_timestamp=NOW,
        configuration_hash=HASH,
        annotation_hash=HASH,
        policy_hash=HASH,
        evaluation_run_id=RUN_ID,
    )


def _finding(result: InvariantResult, *, last_alerted: datetime | None) -> ActiveFinding:
    return ActiveFinding(
        invariant_id=result.invariant_id,
        severity=result.severity,
        state=result.state,
        first_seen=NOW,
        last_seen=NOW,
        occurrence_count=1,
        last_alerted=last_alerted,
        result=result,
    )


def _transition(kind: FindingTransitionKind) -> FindingTransition:
    return FindingTransition(
        invariant_id="RP-CIRC-001",
        kind=kind,
        transition_at=NOW,
        first_seen=NOW,
        evaluation_run_id=RUN_ID,
    )


def _policy(*, alert_unknown: bool = True, recovery: bool = True) -> AlertPolicy:
    return AlertPolicy(
        repeat_critical_after_seconds=3600,
        alert_critical_unknown=alert_unknown,
        send_recovery=recovery,
    )


def test_new_critical_failure_requests_one_p0() -> None:
    result = _result()

    decision = _policy().decide(
        result=result,
        finding=_finding(result, last_alerted=None),
        transition=_transition(FindingTransitionKind.OPENED),
        now=NOW,
    )

    assert decision.action is AlertAction.SEND_NEW
    assert decision.severity == "critical"


def test_persistent_failure_is_skipped_before_repeat_interval() -> None:
    result = _result()

    decision = _policy().decide(
        result=result,
        finding=_finding(result, last_alerted=NOW - timedelta(seconds=3599)),
        transition=None,
        now=NOW,
    )

    assert decision.action is AlertAction.SKIP
    assert "repeat interval" in decision.reason


def test_persistent_failure_repeats_after_interval() -> None:
    result = _result()

    decision = _policy().decide(
        result=result,
        finding=_finding(result, last_alerted=NOW - timedelta(seconds=3600)),
        transition=None,
        now=NOW,
    )

    assert decision.action is AlertAction.SEND_REPEAT


def test_critical_unknown_honors_policy() -> None:
    result = _result(state=InvariantState.UNKNOWN)
    finding = _finding(result, last_alerted=None)
    transition = _transition(FindingTransitionKind.OPENED)

    assert (
        _policy(alert_unknown=True)
        .decide(result=result, finding=finding, transition=transition, now=NOW)
        .action
        is AlertAction.SEND_NEW
    )
    assert (
        _policy(alert_unknown=False)
        .decide(result=result, finding=finding, transition=transition, now=NOW)
        .action
        is AlertAction.SKIP
    )


def test_noncritical_failure_does_not_request_p0() -> None:
    result = _result(severity=Severity.HIGH)

    decision = _policy().decide(
        result=result,
        finding=_finding(result, last_alerted=None),
        transition=_transition(FindingTransitionKind.OPENED),
        now=NOW,
    )

    assert decision.action is AlertAction.SKIP


def test_recovery_is_sent_only_for_recovery_transition() -> None:
    result = _result(state=InvariantState.PASS)

    first = _policy().decide(
        result=result,
        finding=None,
        transition=_transition(FindingTransitionKind.RECOVERED),
        now=NOW,
    )
    repeated = _policy().decide(
        result=result,
        finding=None,
        transition=None,
        now=NOW,
    )

    assert first.action is AlertAction.SEND_RECOVERY
    assert repeated.action is AlertAction.SKIP
