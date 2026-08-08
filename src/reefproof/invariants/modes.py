"""Operating-mode safety invariants."""

from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphFact, ReliabilityGraph


class FiniteServiceModeTimeoutRule:
    invariant_id = "RP-MODE-001"
    version = "1"
    severity = Severity.HIGH
    title = "Service modes must have finite timeouts"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        service_modes = self._service_modes(graph)

        indefinite = tuple(
            (fact, properties)
            for fact, properties in service_modes
            if "timeout_seconds" in properties
            and not self._is_finite_timeout(properties["timeout_seconds"])
        )
        if indefinite:
            affected = tuple(sorted(fact.subject_id for fact, _ in indefinite))
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="A service mode has an indefinite timeout.",
                explanation=(
                    "The following service mode can remain active indefinitely: "
                    f"{', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in indefinite)),
                missing=(),
                action=(
                    "Set a finite timeout appropriate for the maintenance task, "
                    "then verify normal operation resumes when it expires."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        missing_timeout = tuple(
            fact for fact, properties in service_modes if "timeout_seconds" not in properties
        )
        if missing_timeout:
            affected = tuple(sorted(fact.subject_id for fact in missing_timeout))
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Service-mode timeout evidence is incomplete.",
                explanation=(
                    "ReefProof cannot determine the configured timeout for: "
                    f"{', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in missing_timeout)),
                missing=tuple(f"Finite timeout for {names[entity_id]}." for entity_id in affected),
                action="Observe or annotate a finite timeout for every service mode.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get("service_mode_inventory_complete") is True
        )
        if not inventory_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Service-mode timeout safety cannot be proven.",
                explanation=(
                    "No unsafe timeout is visible, but ReefProof lacks evidence "
                    "that every service mode was normalized and classified."
                ),
                affected=tuple(sorted(fact.subject_id for fact, _ in service_modes)),
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in service_modes)),
                missing=("Confirm that every service mode was normalized and classified.",),
                action="Verify service-mode inventory completeness before claiming safety.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every identified service mode has a finite timeout.",
            explanation=(
                "The complete service-mode inventory contains only positive, finite timeout values."
            ),
            affected=tuple(sorted(fact.subject_id for fact, _ in service_modes)),
            evidence=tuple(
                sorted(
                    {
                        *(fact.evidence_ref for fact, _ in service_modes),
                        *inventory_evidence,
                    }
                )
            ),
            missing=(),
            action="No immediate action. Re-evaluate after changing service modes.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @staticmethod
    def _is_finite_timeout(value: JsonValue) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _service_modes(
        graph: ReliabilityGraph,
    ) -> tuple[tuple[GraphFact, dict[str, JsonValue]], ...]:
        service_modes: list[tuple[GraphFact, dict[str, JsonValue]]] = []
        for fact in graph.facts:
            if (
                fact.relationship is RelationshipType.HAS_PROPERTY
                and isinstance(fact.value, dict)
                and fact.value.get("service_mode") is True
            ):
                service_modes.append((fact, fact.value))
        return tuple(service_modes)

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
        return """RP-MODE-001 v1 — Service modes must have finite timeouts

Protects:
  Life-support functions from remaining disabled after maintenance is forgotten.

Required evidence:
  A complete service-mode inventory and each service mode's timeout in seconds.

PASS:
  Every identified service mode has a positive finite timeout.

FAIL:
  A service mode explicitly has no timeout or a non-positive timeout.

UNKNOWN:
  A timeout or confirmation of complete service-mode normalization is missing.

Operator action:
  Configure and verify a finite timeout appropriate for each maintenance task.

Source:
  src/reefproof/invariants/modes.py
Tests:
  tests/unit/test_mode_invariant.py"""
