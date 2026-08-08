"""Unavailable-input fallback invariants."""

from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphFact, ReliabilityGraph


class CriticalOutputFallbackRule:
    invariant_id = "RP-FALLBACK-001"
    version = "1"
    severity = Severity.HIGH
    title = "Critical output fallback behavior must be known and assessed"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        critical_outputs = self._critical_outputs(graph)

        unsafe = tuple(
            fact
            for fact, properties in critical_outputs
            if self._known_behavior(properties)
            and properties.get("unavailable_input_fallback_safe") is False
        )
        if unsafe:
            affected = tuple(sorted(fact.subject_id for fact in unsafe))
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="A critical output has an explicitly unsafe fallback.",
                explanation=(
                    "Unavailable-input fallback is explicitly assessed unsafe for: "
                    f"{', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in unsafe)),
                missing=(),
                action=(
                    "Change the fallback to a reviewed safe behavior or correct an "
                    "inaccurate assessment."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        incomplete: list[tuple[GraphFact, tuple[str, ...]]] = []
        for fact, properties in critical_outputs:
            missing: list[str] = []
            display_name = names[fact.subject_id]
            if not self._known_behavior(properties):
                missing.append(f"Unavailable-input behavior for {display_name}.")
            if not isinstance(properties.get("unavailable_input_fallback_safe"), bool):
                missing.append(
                    f"Safety assessment of unavailable-input fallback for {display_name}."
                )
            if missing:
                incomplete.append((fact, tuple(missing)))
        if incomplete:
            affected = tuple(sorted(fact.subject_id for fact, _ in incomplete))
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Critical unavailable-input fallback evidence is incomplete.",
                explanation=(
                    "ReefProof cannot determine and assess unavailable-input behavior "
                    f"for: {', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in incomplete)),
                missing=tuple(item for _, items in incomplete for item in items),
                action="Observe each fallback behavior and record its safety assessment.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if self._property_is_true(fact, "critical_output_inventory_complete")
        )
        if not inventory_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Critical-output fallback coverage cannot be proven.",
                explanation=(
                    "No unknown fallback is visible, but ReefProof lacks evidence "
                    "that every critical output was normalized and classified."
                ),
                affected=tuple(sorted(fact.subject_id for fact, _ in critical_outputs)),
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in critical_outputs)),
                missing=("Confirm that every critical output was normalized and classified.",),
                action="Verify critical-output inventory completeness before claiming safety.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every critical output has a known, assessed-safe fallback.",
            explanation=(
                "The complete critical-output inventory has explicit unavailable-input "
                "behavior and an authored safe assessment for every output."
            ),
            affected=tuple(sorted(fact.subject_id for fact, _ in critical_outputs)),
            evidence=tuple(
                sorted(
                    {
                        *(fact.evidence_ref for fact, _ in critical_outputs),
                        *inventory_evidence,
                    }
                )
            ),
            missing=(),
            action="No immediate action. Re-evaluate after dependency changes.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @staticmethod
    def _known_behavior(properties: dict[str, JsonValue]) -> bool:
        behavior = properties.get("unavailable_input_behavior")
        return isinstance(behavior, str) and bool(behavior.strip())

    @staticmethod
    def _property_is_true(fact: GraphFact, property_name: str) -> bool:
        return (
            fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get(property_name) is True
        )

    @classmethod
    def _critical_outputs(
        cls,
        graph: ReliabilityGraph,
    ) -> tuple[tuple[GraphFact, dict[str, JsonValue]], ...]:
        outputs: list[tuple[GraphFact, dict[str, JsonValue]]] = []
        for fact in graph.facts:
            if cls._property_is_true(fact, "critical_output") and isinstance(fact.value, dict):
                outputs.append((fact, fact.value))
        return tuple(outputs)

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
        return """RP-FALLBACK-001 v1 — Critical fallback must be known and assessed

Protects:
  Critical functions from unsafe behavior when an input or dependency becomes
  unavailable.

Required evidence:
  Complete critical-output inventory, observed unavailable-input behavior, and
  an explicit human safety assessment.

PASS:
  Every critical output has known behavior explicitly assessed safe.

FAIL:
  A known behavior is explicitly assessed unsafe.

UNKNOWN:
  Behavior, assessment, or critical-output inventory evidence is missing.

Operator action:
  Observe and review each fallback; change behavior that is assessed unsafe.

Source:
  src/reefproof/invariants/fallback.py
Tests:
  tests/unit/test_fallback_invariant.py"""
