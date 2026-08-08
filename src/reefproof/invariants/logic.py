"""Dependency-logic invariants."""

from __future__ import annotations

from datetime import datetime

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import ReliabilityGraph, dependency_cycles


class DependencyCycleRule:
    invariant_id = "RP-LOGIC-001"
    version = "1"
    severity = Severity.CRITICAL
    title = "Dependencies and combiners must not contain cycles"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        cycles = dependency_cycles(graph)
        if cycles:
            cycle = cycles[0]
            names = {node.node_id: node.display_name for node in graph.nodes}
            evidence = tuple(
                edge.evidence_ref
                for edge in graph.edges
                if edge.relationship is RelationshipType.DEPENDS_ON
                and edge.source_id in cycle
                and edge.target_id in cycle
            )
            path = " -> ".join([*(names[node_id] for node_id in cycle), names[cycle[0]]])
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="A dependency cycle is present.",
                explanation=f"The explicit dependency path loops: {path}.",
                affected=cycle,
                evidence=tuple(sorted(evidence)),
                missing=(),
                action=(
                    "Break the cycle in HYDROS dependency or combiner configuration, "
                    "then verify the normalized graph."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        completeness_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get("dependency_map_complete") is True
        )
        if completeness_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.PASS,
                summary="The complete dependency map contains no cycle.",
                explanation=(
                    "No cycle exists among explicit depends_on relationships, and "
                    "authored evidence marks the dependency map complete."
                ),
                affected=(),
                evidence=tuple(sorted(completeness_evidence)),
                missing=(),
                action="No immediate action. Re-evaluate after dependency changes.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.UNKNOWN,
            summary="Dependency-cycle safety cannot be proven.",
            explanation=(
                "No dependency cycle was found, but ReefProof lacks evidence that "
                "the normalized dependency map is complete."
            ),
            affected=(),
            evidence=(),
            missing=("Confirm that all dependency and combiner relationships were normalized.",),
            action="Verify dependency-map completeness before treating the graph as acyclic.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    def _result(
        self,
        *,
        graph: ReliabilityGraph,
        state: InvariantState,
        summary: str,
        explanation: str,
        affected: tuple[str, ...],
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
            affected_entities=affected,
            evidence=evidence,
            missing_evidence=missing,
            recommended_operator_action=action,
            evaluation_timestamp=evaluation_timestamp,
            configuration_hash=graph.configuration_hash,
            annotation_hash=graph.annotation_hash,
            policy_hash=policy_hash,
            evaluation_run_id=evaluation_run_id,
        )

    def explain(self) -> str:
        return """RP-LOGIC-001 v1 — Dependencies must not contain cycles

Protects:
  Deterministic dependency evaluation from circular requirements.

Required evidence:
  All depends_on relationships plus explicit confirmation that dependency and
  combiner normalization is complete.

PASS:
  The complete explicit dependency graph contains no directed cycle.

FAIL:
  One or more explicit dependency paths return to their starting entity.

UNKNOWN:
  No cycle is visible, but dependency-map completeness is not established.

Operator action:
  Break an identified cycle or verify that every dependency and combiner was
  normalized.

Source:
  src/reefproof/invariants/logic.py
Tests:
  tests/unit/test_logic_invariant.py"""
