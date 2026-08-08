"""Flow-dependent load invariants."""

from __future__ import annotations

from datetime import datetime

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphFact, ReliabilityGraph


class FlowPermissiveRule:
    invariant_id: str
    version = "1"
    severity = Severity.CRITICAL
    title: str
    load_property: str
    inventory_property: str
    load_singular: str
    load_plural: str

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        active_uv = tuple(
            fact
            for fact in graph.facts
            if self._property_is_true(fact, self.load_property)
            and self._property_is_true(fact, "active")
        )
        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if self._property_is_true(fact, self.inventory_property)
        )
        dependency_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if self._property_is_true(fact, "dependency_map_complete")
        )
        if not inventory_evidence or not dependency_evidence:
            missing: list[str] = []
            if not inventory_evidence:
                missing.append(
                    f"Confirm that every active {self.load_singular} was normalized and classified."
                )
            if not dependency_evidence:
                missing.append(
                    f"Confirm that every {self.load_singular} dependency was normalized."
                )
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary=f"{self.load_singular.title()} flow-permissive coverage cannot be proven.",
                explanation=(
                    "ReefProof lacks completeness evidence needed to decide whether "
                    f"every active {self.load_singular} depends on confirmed adequate flow."
                ),
                affected=tuple(sorted(fact.subject_id for fact in active_uv)),
                evidence=tuple(sorted(fact.evidence_ref for fact in active_uv)),
                missing=tuple(missing),
                action=(
                    f"Verify active-{self.load_singular} inventory and dependency-map completeness."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        permissive_facts = {
            fact.subject_id: fact
            for fact in graph.facts
            if self._property_is_true(fact, "adequate_flow_permissive")
        }
        protected: dict[str, tuple[str, GraphFact]] = {}
        for uv in active_uv:
            for edge in graph.edges:
                if (
                    edge.source_id == uv.subject_id
                    and edge.relationship is RelationshipType.DEPENDS_ON
                    and edge.target_id in permissive_facts
                ):
                    protected[uv.subject_id] = (
                        edge.evidence_ref,
                        permissive_facts[edge.target_id],
                    )
                    break

        unprotected = tuple(
            sorted(fact.subject_id for fact in active_uv if fact.subject_id not in protected)
        )
        if unprotected:
            uv_evidence = tuple(
                fact.evidence_ref for fact in active_uv if fact.subject_id in unprotected
            )
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary=(
                    f"An active {self.load_singular} can operate without an "
                    "adequate-flow permissive."
                ),
                explanation=(
                    "The complete dependency map contains no adequate-flow permissive for: "
                    f"{', '.join(names[entity_id] for entity_id in unprotected)}."
                ),
                affected=unprotected,
                evidence=tuple(sorted(uv_evidence)),
                missing=(),
                action=(
                    f"Add and verify a dependency that inhibits each {self.load_singular} "
                    "unless "
                    "adequate branch flow is confirmed."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        affected = tuple(
            sorted(
                {
                    entity_id
                    for uv_id, (_, permissive) in protected.items()
                    for entity_id in (uv_id, permissive.subject_id)
                }
            )
        )
        evidence = {
            *inventory_evidence,
            *dependency_evidence,
            *(fact.evidence_ref for fact in active_uv),
        }
        for edge_evidence, permissive in protected.values():
            evidence.add(edge_evidence)
            evidence.add(permissive.evidence_ref)
        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary=(f"Every active {self.load_singular} depends on an adequate-flow permissive."),
            explanation=(
                f"The complete active-{self.load_singular} and dependency evidence "
                "shows a confirmed adequate-flow permissive for every active "
                f"{self.load_singular}."
            ),
            affected=affected,
            evidence=tuple(sorted(evidence)),
            missing=(),
            action=(
                f"No immediate action. Re-evaluate after {self.load_singular} "
                "or flow-control changes."
            ),
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @staticmethod
    def _property_is_true(fact: GraphFact, property_name: str) -> bool:
        return (
            fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get(property_name) is True
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
        raise NotImplementedError


class UvFlowPermissiveRule(FlowPermissiveRule):
    invariant_id = "RP-FLOW-001"
    title = "Active UV loads require an adequate-flow permissive"
    load_property = "uv"
    inventory_property = "active_uv_inventory_complete"
    load_singular = "UV load"
    load_plural = "UV loads"

    def explain(self) -> str:
        return """RP-FLOW-001 v1 — Active UV requires an adequate-flow permissive

Protects:
  UV equipment and the living system from a UV load operating without adequate
  water flow.

Required evidence:
  Complete active-UV and dependency inventories, plus an explicit dependency on
  a fact identified as an adequate-flow permissive.

PASS:
  Every active UV load depends on an adequate-flow permissive.

FAIL:
  A complete dependency map shows an active UV load without that permissive.

UNKNOWN:
  Active-UV inventory or dependency-map completeness is missing.

Operator action:
  Inhibit UV operation unless adequate branch flow is confirmed.

Source:
  src/reefproof/invariants/flow.py
Tests:
  tests/unit/test_uv_invariant.py"""


class ChillerFlowPermissiveRule(FlowPermissiveRule):
    invariant_id = "RP-FLOW-002"
    title = "Active chillers require an adequate-flow permissive"
    load_property = "chiller"
    inventory_property = "active_chiller_inventory_complete"
    load_singular = "chiller"
    load_plural = "chillers"

    def explain(self) -> str:
        return """RP-FLOW-002 v1 — Active chillers require an adequate-flow permissive

Protects:
  Chiller equipment and the living system from a chiller operating without
  confirmed water circulation.

Required evidence:
  Complete active-chiller and dependency inventories, plus an explicit
  dependency on a fact identified as an adequate-flow permissive.

PASS:
  Every active chiller depends on an adequate-flow permissive.

FAIL:
  A complete dependency map shows an active chiller without that permissive.

UNKNOWN:
  Active-chiller inventory or dependency-map completeness is missing.

Operator action:
  Inhibit chiller operation unless adequate utility flow is confirmed.

Source:
  src/reefproof/invariants/flow.py
Tests:
  tests/unit/test_chiller_invariant.py"""
