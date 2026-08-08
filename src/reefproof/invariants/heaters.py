"""Heater safety invariants."""

from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphEdge, GraphFact, ReliabilityGraph


class RedundantHeaterFailureDomainRule:
    invariant_id = "RP-HEAT-001"
    version = "1"
    severity = Severity.CRITICAL
    title = "Redundant heaters must not share a sole failure domain"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        entity_types = {node.node_id: node.entity_type for node in graph.nodes}
        groups = self._heater_groups(graph)
        inventory_complete = any(
            self._property_is_true(fact, "redundant_heater_inventory_complete")
            for fact in graph.facts
        )
        mapping_complete = any(
            self._property_is_true(fact, "heater_failure_domain_map_complete")
            for fact in graph.facts
        )
        if not groups or not inventory_complete or not mapping_complete:
            affected_ids = tuple(
                sorted(fact.subject_id for group in groups.values() for fact in group)
            )
            evidence_refs = tuple(
                sorted(fact.evidence_ref for group in groups.values() for fact in group)
            )
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Redundant-heater independence cannot be proven.",
                explanation=(
                    "ReefProof lacks complete redundant-heater inventory or typed "
                    "failure-domain mapping."
                ),
                affected=affected_ids,
                evidence=evidence_refs,
                missing=(
                    "Confirm redundant-heater inventory and complete failure-domain mapping.",
                ),
                action="Identify redundant heater groups and map every upstream domain.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        for group_name, heaters in sorted(groups.items()):
            heater_ids = sorted(fact.subject_id for fact in heaters)
            for index, first_id in enumerate(heater_ids):
                for second_id in heater_ids[index + 1 :]:
                    first_domains = self._domains(graph, first_id, entity_types)
                    second_domains = self._domains(graph, second_id, entity_types)
                    for category in sorted(first_domains.keys() & second_domains.keys()):
                        shared = sorted(
                            first_domains[category].keys() & second_domains[category].keys()
                        )
                        if not shared:
                            continue
                        domain_id = shared[0]
                        return self._result(
                            graph=graph,
                            state=InvariantState.FAIL,
                            summary="Redundant heaters share a failure domain.",
                            explanation=(
                                f"{names[first_id]} and {names[second_id]} in redundancy "
                                f"group {group_name!r} share {category.replace('_', ' ')} "
                                f"{names[domain_id]}."
                            ),
                            affected=(first_id, second_id, domain_id),
                            evidence=tuple(
                                sorted(
                                    {
                                        first_domains[category][domain_id],
                                        second_domains[category][domain_id],
                                    }
                                )
                            ),
                            missing=(),
                            action=(
                                "Move one heater to an independent power, control, "
                                "sensor, and dependency path as applicable."
                            ),
                            evaluation_timestamp=evaluation_timestamp,
                            evaluation_run_id=evaluation_run_id,
                            policy_hash=policy_hash,
                        )

        affected_ids_set: set[str] = set()
        evidence_refs_set: set[str] = set()
        for heaters in groups.values():
            for fact in heaters:
                affected_ids_set.add(fact.subject_id)
                evidence_refs_set.add(fact.evidence_ref)
                for domains in self._domains(graph, fact.subject_id, entity_types).values():
                    affected_ids_set.update(domains)
                    evidence_refs_set.update(domains.values())
        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Redundant heaters use independent mapped failure domains.",
            explanation=(
                "No redundant heater pair shares a mapped power domain, controller, "
                "sole control sensor, or sole dependency."
            ),
            affected=tuple(sorted(affected_ids_set)),
            evidence=tuple(sorted(evidence_refs_set)),
            missing=(),
            action="No immediate action. Re-evaluate after heater-path changes.",
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

    @staticmethod
    def _heater_groups(graph: ReliabilityGraph) -> dict[str, tuple[GraphFact, ...]]:
        groups: dict[str, list[GraphFact]] = {}
        for fact in graph.facts:
            if fact.relationship is not RelationshipType.HAS_PROPERTY:
                continue
            if not isinstance(fact.value, dict):
                continue
            group = fact.value.get("heater_redundancy_group")
            if fact.value.get("heater") is True and isinstance(group, str) and group:
                groups.setdefault(group, []).append(fact)
        return {
            name: tuple(sorted(facts, key=lambda fact: fact.subject_id))
            for name, facts in groups.items()
        }

    @staticmethod
    def _domains(
        graph: ReliabilityGraph,
        heater_id: str,
        entity_types: dict[str, EntityType],
    ) -> dict[str, dict[str, str]]:
        domains: dict[str, dict[str, str]] = {}
        for edge in graph.edges:
            if edge.source_id != heater_id:
                continue
            category = RedundantHeaterFailureDomainRule._domain_category(edge, entity_types)
            if category is not None:
                domains.setdefault(category, {})[edge.target_id] = edge.evidence_ref
        return domains

    @staticmethod
    def _domain_category(
        edge: GraphEdge,
        entity_types: dict[str, EntityType],
    ) -> str | None:
        if edge.relationship is RelationshipType.POWERED_BY:
            return "power_domain"
        if edge.relationship is RelationshipType.CONTROLLED_BY:
            return "controller"
        if edge.relationship is RelationshipType.DEPENDS_ON:
            if entity_types.get(edge.target_id) is EntityType.SENSOR:
                return "sole_control_sensor"
            return "sole_dependency"
        return None

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
        return """RP-HEAT-001 v1 — Redundant heaters need independent failure domains

Protects:
  Temperature control from one electrical, controller, sensor, or dependency
  failure removing both intended heater paths.

Required evidence:
  Complete redundant-heater groups and typed power, controller, sensor, and
  dependency mappings.

PASS:
  No redundant heater pair shares a mapped sole failure domain.

FAIL:
  A redundant pair shares a power domain, controller, sole sensor, or dependency.

UNKNOWN:
  Heater inventory or failure-domain mapping is incomplete.

Operator action:
  Separate the correlated path or correct inaccurate physical annotations.

Source:
  src/reefproof/invariants/heaters.py
Tests:
  tests/unit/test_heater_redundancy_invariant.py"""


class IndependentHeaterSafeguardRule:
    invariant_id = "RP-HEAT-002"
    version = "1"
    severity = Severity.HIGH
    title = "Active heaters require an independent safeguard"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        active_heaters = self._active_heaters(graph)

        unprotected = tuple(
            fact
            for fact, properties in active_heaters
            if properties.get("independent_safeguard") is False
        )
        if unprotected:
            affected = tuple(sorted(fact.subject_id for fact in unprotected))
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="An active heater has no independent safeguard.",
                explanation=(
                    "Independent over-temperature protection is confirmed absent for: "
                    f"{', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in unprotected)),
                missing=(),
                action=(
                    "Disable the unprotected heater if safe to do so, then install "
                    "and verify an independent thermostat or high-limit safeguard."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        unconfirmed = tuple(
            fact
            for fact, properties in active_heaters
            if properties.get("independent_safeguard") is not True
        )
        if unconfirmed:
            affected = tuple(sorted(fact.subject_id for fact in unconfirmed))
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Independent heater safeguard evidence is incomplete.",
                explanation=(
                    "ReefProof cannot confirm independent over-temperature protection "
                    f"for: {', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in unconfirmed)),
                missing=tuple(
                    f"Independent thermostat or high-limit safeguard for {names[entity_id]}."
                    for entity_id in affected
                ),
                action=(
                    "Physically verify and annotate the independent safeguard for "
                    "every active heater."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get("active_heater_inventory_complete") is True
        )
        if not inventory_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Active-heater safeguard coverage cannot be proven.",
                explanation=(
                    "No unprotected heater is visible, but ReefProof lacks evidence "
                    "that every active heater was normalized and classified."
                ),
                affected=tuple(sorted(fact.subject_id for fact, _ in active_heaters)),
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in active_heaters)),
                missing=("Confirm that every active heater was normalized and classified.",),
                action="Verify active-heater inventory completeness before claiming safety.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every active heater has a confirmed independent safeguard.",
            explanation=(
                "The complete active-heater inventory confirms an independent "
                "thermostat or high-limit safeguard for every heater."
            ),
            affected=tuple(sorted(fact.subject_id for fact, _ in active_heaters)),
            evidence=tuple(
                sorted(
                    {
                        *(fact.evidence_ref for fact, _ in active_heaters),
                        *inventory_evidence,
                    }
                )
            ),
            missing=(),
            action="No immediate action. Re-verify safeguards after heater changes.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @staticmethod
    def _active_heaters(
        graph: ReliabilityGraph,
    ) -> tuple[tuple[GraphFact, dict[str, JsonValue]], ...]:
        heaters: list[tuple[GraphFact, dict[str, JsonValue]]] = []
        for fact in graph.facts:
            if (
                fact.relationship is RelationshipType.HAS_PROPERTY
                and isinstance(fact.value, dict)
                and fact.value.get("heater") is True
                and fact.value.get("active") is True
            ):
                heaters.append((fact, fact.value))
        return tuple(heaters)

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
        return """RP-HEAT-002 v1 — Active heaters require an independent safeguard

Protects:
  The living system from a controller, sensor, or configuration failure leaving
  a heater energized.

Required evidence:
  A complete active-heater inventory and physical confirmation of an independent
  thermostat or high-limit safeguard for each heater.

PASS:
  Every active heater has a confirmed independent safeguard.

FAIL:
  An active heater is confirmed to have no independent safeguard.

UNKNOWN:
  Safeguard confirmation or active-heater inventory evidence is missing.

Operator action:
  Verify each physical safeguard and install one where confirmed absent.

Source:
  src/reefproof/invariants/heaters.py
Tests:
  tests/unit/test_heater_invariant.py"""
