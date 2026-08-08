"""Circulation reliability invariants."""

from __future__ import annotations

from datetime import datetime

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphFact, ReliabilityGraph


class RedundantReturnsPowerDomainRule:
    invariant_id = "RP-CIRC-001"
    version = "1"
    severity = Severity.CRITICAL
    title = "Redundant returns must not share one power domain"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        redundant_edges = [
            edge for edge in graph.edges if edge.relationship is RelationshipType.REDUNDANT_WITH
        ]
        if not redundant_edges:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Intended redundant returns are not identified.",
                explanation=(
                    "ReefProof cannot evaluate shared return-pump failure domains "
                    "without an explicit redundant_with annotation."
                ),
                affected=(),
                evidence=(),
                missing=("Identify the intended redundant return pair.",),
                action="Add or verify the return redundancy annotation.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        passes: list[tuple[str, str, set[str]]] = []
        for redundant in redundant_edges:
            first_power = self._power_domains(graph, redundant.source_id)
            second_power = self._power_domains(graph, redundant.target_id)
            missing: list[str] = []
            if not first_power:
                missing.append(f"Power domain for {names[redundant.source_id]}.")
            if not second_power:
                missing.append(f"Power domain for {names[redundant.target_id]}.")
            if missing:
                return self._result(
                    graph=graph,
                    state=InvariantState.UNKNOWN,
                    summary="Return power-domain evidence is incomplete.",
                    explanation=(
                        f"{names[redundant.source_id]} and {names[redundant.target_id]} "
                        "are intended redundant returns, but their independent power "
                        "domains cannot be proven."
                    ),
                    affected=(redundant.source_id, redundant.target_id),
                    evidence=(f"Redundancy evidence: {redundant.evidence_ref}",),
                    missing=tuple(missing),
                    action="Verify and annotate the power domain for each return.",
                    evaluation_timestamp=evaluation_timestamp,
                    evaluation_run_id=evaluation_run_id,
                    policy_hash=policy_hash,
                )

            shared = first_power.keys() & second_power.keys()
            if shared:
                failure_domain_id = sorted(shared)[0]
                return self._result(
                    graph=graph,
                    state=InvariantState.FAIL,
                    summary="Intended redundant returns share one power domain.",
                    explanation=(
                        f"{names[redundant.source_id]} and {names[redundant.target_id]} "
                        f"are both powered by {names[failure_domain_id]}."
                    ),
                    affected=(
                        redundant.source_id,
                        redundant.target_id,
                        failure_domain_id,
                    ),
                    evidence=(
                        f"Redundancy evidence: {redundant.evidence_ref}",
                        f"{names[redundant.source_id]} power evidence: "
                        f"{first_power[failure_domain_id]}",
                        f"{names[redundant.target_id]} power evidence: "
                        f"{second_power[failure_domain_id]}",
                    ),
                    missing=(),
                    action=(
                        "Move one return to an independent power domain or correct "
                        "the physical-system annotations."
                    ),
                    evaluation_timestamp=evaluation_timestamp,
                    evaluation_run_id=evaluation_run_id,
                    policy_hash=policy_hash,
                )
            passes.append(
                (
                    redundant.source_id,
                    redundant.target_id,
                    set(first_power) | set(second_power),
                )
            )

        affected = tuple(
            sorted(
                {
                    entity_id
                    for first_id, second_id, domains in passes
                    for entity_id in (first_id, second_id, *domains)
                }
            )
        )
        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Intended redundant returns use distinct power domains.",
            explanation=(
                "Every explicitly identified redundant return pair has complete "
                "and non-overlapping power-domain annotations."
            ),
            affected=affected,
            evidence=tuple(
                edge.evidence_ref
                for edge in graph.edges
                if edge.relationship
                in {RelationshipType.REDUNDANT_WITH, RelationshipType.POWERED_BY}
            ),
            missing=(),
            action="No immediate action. Re-verify annotations after electrical changes.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @staticmethod
    def _power_domains(graph: ReliabilityGraph, subject_id: str) -> dict[str, str]:
        return {
            edge.target_id: edge.evidence_ref
            for edge in graph.edges
            if edge.source_id == subject_id and edge.relationship is RelationshipType.POWERED_BY
        }

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
        return """RP-CIRC-001 v1 — Redundant returns must not share one power domain

Protects:
  Survival circulation from one electrical failure removing all intended returns.

Required evidence:
  An explicit redundant_with relationship and one powered_by relationship for
  each return.

PASS:
  Each intended redundant return has a distinct annotated power domain.

FAIL:
  Two intended redundant returns share an annotated power domain.

UNKNOWN:
  The redundant pair or either power-domain annotation is missing.

Operator action:
  Verify the physical annotations. If correct, move one return to an independent
  power domain.

Source:
  src/reefproof/invariants/circulation.py
Tests:
  tests/unit/test_invariants.py"""


class LowPowerCirculationRule:
    invariant_id = "RP-CIRC-003"
    version = "1"
    severity = Severity.CRITICAL
    title = "Low Power must retain battery-approved circulation"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        low_power_facts = tuple(
            fact for fact in graph.facts if self._property_is_true(fact, "low_power_mode")
        )
        inventory_complete = any(
            self._property_is_true(fact, "low_power_mode_inventory_complete")
            for fact in graph.facts
        )
        membership_complete = any(
            self._property_is_true(fact, "mode_membership_complete") for fact in graph.facts
        )
        if not low_power_facts or not inventory_complete or not membership_complete:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Low Power circulation coverage cannot be proven.",
                explanation=(
                    "ReefProof lacks explicit evidence identifying Low Power and "
                    "confirming that its complete output membership was normalized."
                ),
                affected=tuple(sorted(fact.subject_id for fact in low_power_facts)),
                evidence=tuple(sorted(fact.evidence_ref for fact in low_power_facts)),
                missing=("Confirm the Low Power mode and its complete output membership.",),
                action="Identify Low Power and verify every active-in-mode relationship.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        approved = {
            fact.subject_id: fact
            for fact in graph.facts
            if self._property_is_true(fact, "battery_approved_circulation")
        }
        active_approved: dict[str, tuple[str, GraphFact]] = {}
        low_power_ids = {fact.subject_id for fact in low_power_facts}
        for edge in graph.edges:
            if (
                edge.relationship is RelationshipType.ACTIVE_IN
                and edge.target_id in low_power_ids
                and edge.source_id in approved
            ):
                active_approved[edge.source_id] = (
                    edge.evidence_ref,
                    approved[edge.source_id],
                )

        if not active_approved:
            affected = tuple(sorted(low_power_ids))
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="Low Power contains no battery-approved circulation.",
                explanation=(
                    "The complete mode membership for "
                    f"{', '.join(names[mode_id] for mode_id in affected)} contains no "
                    "device explicitly approved for useful battery-backed circulation."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in low_power_facts)),
                missing=(),
                action=(
                    "Add and test a battery-backed circulation device in Low Power, "
                    "or correct inaccurate mode annotations."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        device_ids = set(active_approved)
        affected = tuple(sorted({*low_power_ids, *device_ids}))
        evidence = {fact.evidence_ref for fact in low_power_facts}
        for edge_evidence, approved_fact in active_approved.values():
            evidence.add(edge_evidence)
            evidence.add(approved_fact.evidence_ref)
        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Low Power retains battery-approved circulation.",
            explanation=(
                "At least one explicitly battery-approved circulation device is active "
                "in the complete Low Power mode membership."
            ),
            affected=affected,
            evidence=tuple(sorted(evidence)),
            missing=(),
            action="No immediate action. Re-test after battery or mode changes.",
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
        return """RP-CIRC-003 v1 — Low Power must retain useful circulation

Protects:
  Oxygenation and water movement during a mains-power interruption.

Required evidence:
  Identified Low Power mode, complete mode membership, and an explicit
  battery-approved-circulation annotation.

PASS:
  A battery-approved circulation device is active in Low Power.

FAIL:
  Complete Low Power membership contains no approved circulation device.

UNKNOWN:
  Low Power identity or membership completeness is missing.

Operator action:
  Add and test battery-backed circulation or correct physical annotations.

Source:
  src/reefproof/invariants/circulation.py
Tests:
  tests/unit/test_low_power_invariant.py"""


class SurvivingCirculationPathRule:
    invariant_id = "RP-CIRC-002"
    version = "1"
    severity = Severity.CRITICAL
    title = "Every evaluated operating mode must retain circulation or oxygenation"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        mode_facts = tuple(
            fact for fact in graph.facts if self._property_is_true(fact, "evaluated_operating_mode")
        )
        completeness_properties = (
            "operating_mode_inventory_complete",
            "mode_membership_complete",
            "circulation_function_inventory_complete",
        )
        complete = all(
            any(self._property_is_true(fact, property_name) for fact in graph.facts)
            for property_name in completeness_properties
        )
        if not mode_facts or not complete:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Surviving circulation paths cannot be proven.",
                explanation=(
                    "ReefProof lacks complete operating-mode, membership, or approved "
                    "circulation and oxygenation inventory evidence."
                ),
                affected=tuple(sorted(fact.subject_id for fact in mode_facts)),
                evidence=tuple(sorted(fact.evidence_ref for fact in mode_facts)),
                missing=(
                    "Confirm operating modes, memberships, and approved circulation inventory.",
                ),
                action="Complete mode and life-support inventory before claiming coverage.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        approved = {
            fact.subject_id: fact
            for fact in graph.facts
            if self._property_is_true(fact, "approved_circulation_or_oxygenation")
        }
        active_by_mode: dict[str, dict[str, tuple[str, GraphFact]]] = {
            fact.subject_id: {} for fact in mode_facts
        }
        for edge in graph.edges:
            if (
                edge.relationship is RelationshipType.ACTIVE_IN
                and edge.target_id in active_by_mode
                and edge.source_id in approved
            ):
                active_by_mode[edge.target_id][edge.source_id] = (
                    edge.evidence_ref,
                    approved[edge.source_id],
                )

        unsafe_modes = tuple(
            sorted(mode_id for mode_id, devices in active_by_mode.items() if not devices)
        )
        if unsafe_modes:
            mode_evidence = tuple(
                fact.evidence_ref for fact in mode_facts if fact.subject_id in unsafe_modes
            )
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="An operating mode has no surviving circulation path.",
                explanation=(
                    "The complete mode rules contain no approved circulation or "
                    "oxygenation function in: "
                    f"{', '.join(names[mode_id] for mode_id in unsafe_modes)}."
                ),
                affected=unsafe_modes,
                evidence=tuple(sorted(mode_evidence)),
                missing=(),
                action=(
                    "Restore at least one approved circulation or oxygenation function "
                    "to every operating mode."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        affected = set(active_by_mode)
        evidence = {fact.evidence_ref for fact in mode_facts}
        for devices in active_by_mode.values():
            affected.update(devices)
            for edge_evidence, approved_fact in devices.values():
                evidence.add(edge_evidence)
                evidence.add(approved_fact.evidence_ref)
        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every operating mode retains circulation or oxygenation.",
            explanation=(
                "Each evaluated operating mode has at least one explicitly approved "
                "circulation or oxygenation function in its complete membership."
            ),
            affected=tuple(sorted(affected)),
            evidence=tuple(sorted(evidence)),
            missing=(),
            action="No immediate action. Re-evaluate after mode changes.",
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
        return """RP-CIRC-002 v1 — Every mode needs surviving circulation

Protects:
  Livestock oxygenation and exchange from a mode configuration that removes all
  approved water movement.

Required evidence:
  Complete operating modes, mode membership, and approved circulation or
  oxygenation functions.

PASS:
  Every evaluated mode contains at least one approved function.

FAIL:
  A complete evaluated mode contains no approved function.

UNKNOWN:
  Mode, membership, or circulation-function evidence is incomplete.

Operator action:
  Restore an approved circulation or oxygenation function in every mode.

Source:
  src/reefproof/invariants/circulation.py
Tests:
  tests/unit/test_surviving_circulation_invariant.py"""
