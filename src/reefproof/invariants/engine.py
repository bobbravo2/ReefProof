"""Evaluate the registered invariant set."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.invariants.registry import registered_rules
from reefproof.reliability import ReliabilityGraph


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    evaluation_run_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    evaluation_timestamp: datetime
    policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    results: tuple[InvariantResult, ...]


def _policy_hash() -> str:
    policy = [
        {
            "invariant_id": rule.invariant_id,
            "version": rule.version,
            "severity": rule.severity.value,
        }
        for rule in registered_rules()
    ]
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def evaluate_graph(
    graph: ReliabilityGraph,
    *,
    evaluation_timestamp: datetime | None = None,
    evaluation_run_id: str | None = None,
) -> EvaluationRun:
    timestamp = evaluation_timestamp or datetime.now(UTC)
    run_id = evaluation_run_id or str(uuid.uuid4())
    policy_hash = _policy_hash()
    results = tuple(
        rule.evaluate(
            graph,
            evaluation_timestamp=timestamp,
            evaluation_run_id=run_id,
            policy_hash=policy_hash,
        )
        for rule in registered_rules()
    )
    return EvaluationRun(
        evaluation_run_id=run_id,
        evaluation_timestamp=timestamp,
        policy_hash=policy_hash,
        results=results,
    )


def result_exit_code(
    results: tuple[InvariantResult, ...],
    *,
    fail_on: Severity = Severity.CRITICAL,
) -> int:
    rank = {
        Severity.INFO: 0,
        Severity.WARNING: 1,
        Severity.HIGH: 2,
        Severity.CRITICAL: 3,
    }
    selected = tuple(result for result in results if rank[result.severity] >= rank[fail_on])
    failures = {result.severity for result in selected if result.state is InvariantState.FAIL}
    if Severity.CRITICAL in failures:
        return 40
    if Severity.HIGH in failures:
        return 30
    if Severity.WARNING in failures:
        return 20
    if any(result.state is InvariantState.UNKNOWN for result in selected):
        return 10
    return 0
