from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime
from pathlib import Path

from reefproof.alerting import (
    AlertCoordinator,
    AlertPolicy,
    ConsoleAlertAdapter,
    DeliveryStatus,
)
from reefproof.invariants import EvaluationRun, InvariantResult, InvariantState, Severity
from reefproof.storage import Database, FindingTransitionKind

NOW = datetime.fromisoformat("2026-07-25T20:30:00-04:00")
RUN_ID = "22345678-abcd-4234-8234-123456789abc"
HASH = f"sha256:{'b' * 64}"
ENTITY_ID = "RP.DEVICE.0123456789abcdef"


def _result() -> InvariantResult:
    return InvariantResult(
        invariant_id="RP-CIRC-001",
        version="1",
        severity=Severity.CRITICAL,
        state=InvariantState.FAIL,
        summary="Both display returns share one power domain.",
        detailed_explanation="Return A and Return B share MAIN-6.",
        affected_entities=(ENTITY_ID,),
        evidence=("RP.ANNOTATION.0123456789abcdef",),
        missing_evidence=(),
        recommended_operator_action="Restore independent return-pump power domains.",
        evaluation_timestamp=NOW,
        configuration_hash=HASH,
        annotation_hash=HASH,
        policy_hash=HASH,
        evaluation_run_id=RUN_ID,
    )


def _setup(path: Path):
    database = Database(path)
    database.migrate()
    result = _result()
    run = EvaluationRun(
        evaluation_run_id=RUN_ID,
        evaluation_timestamp=NOW,
        policy_hash=HASH,
        results=(result,),
    )
    transitions = database.record_evaluation(run)
    finding = database.active_finding(result.invariant_id)
    transition = next(item for item in transitions if item.kind is FindingTransitionKind.OPENED)
    assert finding is not None
    return database, result, finding, transition


def test_console_coordinator_delivers_human_readable_event_and_records_success(
    tmp_path: Path,
) -> None:
    database, result, finding, transition = _setup(tmp_path / "reefproof.sqlite3")
    stream = io.StringIO()
    coordinator = AlertCoordinator(
        database=database,
        policy=AlertPolicy(
            repeat_critical_after_seconds=3600,
            alert_critical_unknown=True,
            send_recovery=True,
        ),
        adapter=ConsoleAlertAdapter(stream),
        reefproof_base_url="http://reefproof.local",
    )

    delivery = asyncio.run(
        coordinator.process(
            result=result,
            finding=finding,
            transition=transition,
            entity_names={ENTITY_ID: "Return A"},
            now=NOW,
        )
    )

    event = json.loads(stream.getvalue())
    assert delivery.status is DeliveryStatus.SUCCESS
    assert event["source"] == "ReefProof"
    assert event["affected_entities"] == ["Return A"]
    assert event["reefproof_url"].endswith("/v1/findings/RP-CIRC-001")
    assert database.alert_attempt_count("RP-CIRC-001") == 1
    updated = database.active_finding("RP-CIRC-001")
    assert updated is not None
    assert updated.last_alerted == NOW


class _FailingAdapter:
    name = "failing"

    async def send(self, event: object) -> None:
        raise RuntimeError("synthetic adapter failure")


class _RecordingAdapter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.events: list[object] = []

    async def send(self, event: object) -> None:
        self.events.append(event)


def test_failed_delivery_is_stored_without_marking_finding_alerted(tmp_path: Path) -> None:
    database, result, finding, transition = _setup(tmp_path / "reefproof.sqlite3")
    coordinator = AlertCoordinator(
        database=database,
        policy=AlertPolicy(
            repeat_critical_after_seconds=3600,
            alert_critical_unknown=True,
            send_recovery=True,
        ),
        adapter=_FailingAdapter(),
        reefproof_base_url="http://reefproof.local",
    )

    delivery = asyncio.run(
        coordinator.process(
            result=result,
            finding=finding,
            transition=transition,
            entity_names={},
            now=NOW,
        )
    )

    assert delivery.status is DeliveryStatus.FAILURE
    assert database.alert_attempt_count("RP-CIRC-001") == 1
    updated = database.active_finding("RP-CIRC-001")
    assert updated is not None
    assert updated.last_alerted is None


def test_each_adapter_has_independent_delivery_and_retry_state(tmp_path: Path) -> None:
    database_path = tmp_path / "reefproof.sqlite3"
    database, result, finding, transition = _setup(database_path)
    successful = _RecordingAdapter("console")
    failing = _FailingAdapter()
    policy = AlertPolicy(
        repeat_critical_after_seconds=3600,
        alert_critical_unknown=True,
        send_recovery=True,
    )
    successful_coordinator = AlertCoordinator(
        database=database,
        policy=policy,
        adapter=successful,
        reefproof_base_url="http://reefproof.local",
    )
    failing_coordinator = AlertCoordinator(
        database=database,
        policy=policy,
        adapter=failing,
        reefproof_base_url="http://reefproof.local",
    )

    first_success = asyncio.run(
        successful_coordinator.process(
            result=result,
            finding=finding,
            transition=transition,
            entity_names={},
            now=NOW,
        )
    )
    first_failure = asyncio.run(
        failing_coordinator.process(
            result=result,
            finding=database.active_finding(result.invariant_id),
            transition=transition,
            entity_names={},
            now=NOW,
        )
    )
    restarted_database = Database(database_path)
    restarted_failing_coordinator = AlertCoordinator(
        database=restarted_database,
        policy=policy,
        adapter=failing,
        reefproof_base_url="http://reefproof.local",
    )
    retry_failure = asyncio.run(
        restarted_failing_coordinator.process(
            result=result,
            finding=restarted_database.active_finding(result.invariant_id),
            transition=None,
            entity_names={},
            now=NOW,
        )
    )

    assert first_success.status is DeliveryStatus.SUCCESS
    assert first_failure.status is DeliveryStatus.FAILURE
    assert retry_failure.status is DeliveryStatus.FAILURE
    assert len(successful.events) == 1
    assert database.alert_attempt_count("RP-CIRC-001") == 3
