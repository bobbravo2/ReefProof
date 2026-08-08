"""Narrow protocol for explicit Python invariants."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from reefproof.invariants.models import InvariantResult, Severity
from reefproof.reliability import ReliabilityGraph


class InvariantRule(Protocol):
    invariant_id: str
    version: str
    severity: Severity
    title: str

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult: ...

    def explain(self) -> str: ...
