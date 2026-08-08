"""Water-addition safety invariants."""

from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue

from reefproof.configuration import RelationshipType
from reefproof.invariants.models import InvariantResult, InvariantState, Severity
from reefproof.reliability import GraphFact, ReliabilityGraph


class BoundedAtoAdditionRule:
    invariant_id = "RP-WATER-001"
    version = "1"
    severity = Severity.CRITICAL
    title = "Active ATO paths must bound freshwater addition"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        active_ato = self._active_ato(graph)

        unsafe: list[tuple[GraphFact, tuple[str, ...]]] = []
        incomplete: list[tuple[GraphFact, tuple[str, ...]]] = []
        for fact, properties in active_ato:
            confirmed_absent, missing = self._classify_bounds(names[fact.subject_id], properties)
            if confirmed_absent:
                unsafe.append((fact, confirmed_absent))
            elif missing:
                incomplete.append((fact, missing))

        if unsafe:
            affected = tuple(sorted(fact.subject_id for fact, _ in unsafe))
            failures = sorted({item for _, items in unsafe for item in items})
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="An active ATO path has an unbounded freshwater-addition risk.",
                explanation=(f"Confirmed unsafe ATO controls: {'; '.join(failures)}."),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in unsafe)),
                missing=(),
                action=(
                    "Disable automated addition if safe, then configure a finite "
                    "runtime or volume bound plus high-water and independent high stops."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        if incomplete:
            affected = tuple(sorted(fact.subject_id for fact, _ in incomplete))
            missing = tuple(sorted({item for _, items in incomplete for item in items}))
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="ATO freshwater-addition bounds cannot be proven.",
                explanation=(
                    "One or more active ATO paths lack evidence required to calculate "
                    "and independently stop freshwater addition."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in incomplete)),
                missing=missing,
                action="Observe or annotate every required ATO bound and independent stop.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if self._property_is_true(fact, "active_ato_inventory_complete")
        )
        if not inventory_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="ATO freshwater-addition coverage cannot be proven.",
                explanation=(
                    "No unbounded ATO is visible, but ReefProof lacks evidence that "
                    "every active ATO path was normalized and classified."
                ),
                affected=tuple(sorted(fact.subject_id for fact, _ in active_ato)),
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in active_ato)),
                missing=("Confirm that every active ATO path was normalized and classified.",),
                action="Verify active-ATO inventory completeness before claiming safety.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every active ATO path has bounded freshwater addition.",
            explanation=(
                "The complete active-ATO inventory has a finite runtime, measurable "
                "flow or volume bound, high-water inhibit, and independent high stop."
            ),
            affected=tuple(sorted(fact.subject_id for fact, _ in active_ato)),
            evidence=tuple(
                sorted(
                    {
                        *(fact.evidence_ref for fact, _ in active_ato),
                        *inventory_evidence,
                    }
                )
            ),
            missing=(),
            action="No immediate action. Re-evaluate after ATO configuration changes.",
            evaluation_timestamp=evaluation_timestamp,
            evaluation_run_id=evaluation_run_id,
            policy_hash=policy_hash,
        )

    @classmethod
    def _classify_bounds(
        cls,
        display_name: str,
        properties: dict[str, JsonValue],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        unsafe: list[str] = []
        missing: list[str] = []
        cls._classify_positive(
            properties,
            "maximum_runtime_seconds",
            f"maximum runtime for {display_name}",
            unsafe,
            missing,
        )

        flow_keys = ("pump_flow_liters_per_hour", "maximum_addition_liters")
        present_flow = [properties[key] for key in flow_keys if key in properties]
        if not present_flow:
            missing.append(f"Pump flow or maximum-addition-volume evidence for {display_name}.")
        elif not any(cls._is_positive_number(value) for value in present_flow):
            unsafe.append(f"pump flow or maximum addition volume for {display_name}")

        for key, label in (
            ("high_water_inhibit", "high-water inhibit"),
            ("independent_high_stop", "independent high stop"),
        ):
            if key not in properties:
                missing.append(f"{label.capitalize()} evidence for {display_name}.")
            elif properties[key] is not True:
                unsafe.append(f"{label} for {display_name}")
        return tuple(unsafe), tuple(missing)

    @classmethod
    def _classify_positive(
        cls,
        properties: dict[str, JsonValue],
        key: str,
        label: str,
        unsafe: list[str],
        missing: list[str],
    ) -> None:
        if key not in properties:
            missing.append(f"{label.capitalize()} evidence.")
        elif not cls._is_positive_number(properties[key]):
            unsafe.append(label)

    @staticmethod
    def _is_positive_number(value: JsonValue) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    @staticmethod
    def _property_is_true(fact: GraphFact, property_name: str) -> bool:
        return (
            fact.relationship is RelationshipType.HAS_PROPERTY
            and isinstance(fact.value, dict)
            and fact.value.get(property_name) is True
        )

    @classmethod
    def _active_ato(
        cls,
        graph: ReliabilityGraph,
    ) -> tuple[tuple[GraphFact, dict[str, JsonValue]], ...]:
        paths: list[tuple[GraphFact, dict[str, JsonValue]]] = []
        for fact in graph.facts:
            if (
                cls._property_is_true(fact, "ato")
                and cls._property_is_true(fact, "active")
                and isinstance(fact.value, dict)
            ):
                paths.append((fact, fact.value))
        return tuple(paths)

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
        return """RP-WATER-001 v1 — Active ATO must bound freshwater addition

Protects:
  Salinity and system water level from an uncontrolled freshwater addition.

Required evidence:
  Complete active-ATO inventory, finite maximum runtime, pump flow or maximum
  volume, high-water inhibit, and an independent high stop.

PASS:
  Every active ATO path has all four independently evidenced bounds.

FAIL:
  A required bound or stop is explicitly absent or non-positive.

UNKNOWN:
  A required value or active-ATO inventory evidence is missing.

Operator action:
  Bound addition and independently stop it at both high-water levels.

Source:
  src/reefproof/invariants/water.py
Tests:
  tests/unit/test_ato_invariant.py"""


class IndependentRodiHighHighRule:
    invariant_id = "RP-WATER-002"
    version = "1"
    severity = Severity.CRITICAL
    title = "Automated RODI fills require an independent high-high cutoff"

    def evaluate(
        self,
        graph: ReliabilityGraph,
        *,
        evaluation_timestamp: datetime,
        evaluation_run_id: str,
        policy_hash: str,
    ) -> InvariantResult:
        names = {node.node_id: node.display_name for node in graph.nodes}
        automated_fills = self._automated_fills(graph)
        unprotected = tuple(
            fact
            for fact, properties in automated_fills
            if properties.get("independent_high_high_cutoff") is False
        )
        if unprotected:
            affected = tuple(sorted(fact.subject_id for fact in unprotected))
            return self._result(
                graph=graph,
                state=InvariantState.FAIL,
                summary="An automated RODI fill has no independent high-high cutoff.",
                explanation=(
                    "Independent final overflow protection is confirmed absent for: "
                    f"{', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in unprotected)),
                missing=(),
                action=(
                    "Disable automated production if safe, then install and verify "
                    "an independent final high-high cutoff."
                ),
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        unconfirmed = tuple(
            fact
            for fact, properties in automated_fills
            if properties.get("independent_high_high_cutoff") is not True
        )
        if unconfirmed:
            affected = tuple(sorted(fact.subject_id for fact in unconfirmed))
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="RODI high-high cutoff evidence is incomplete.",
                explanation=(
                    "ReefProof cannot confirm independent final overflow protection "
                    f"for: {', '.join(names[entity_id] for entity_id in affected)}."
                ),
                affected=affected,
                evidence=tuple(sorted(fact.evidence_ref for fact in unconfirmed)),
                missing=tuple(
                    f"Independent high-high cutoff for {names[entity_id]}."
                    for entity_id in affected
                ),
                action="Physically verify and annotate each independent high-high cutoff.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        inventory_evidence = tuple(
            fact.evidence_ref
            for fact in graph.facts
            if self._property_is_true(fact, "automated_rodi_inventory_complete")
        )
        if not inventory_evidence:
            return self._result(
                graph=graph,
                state=InvariantState.UNKNOWN,
                summary="Automated RODI high-high coverage cannot be proven.",
                explanation=(
                    "No unprotected fill is visible, but ReefProof lacks evidence "
                    "that every automated RODI fill was normalized and classified."
                ),
                affected=tuple(sorted(fact.subject_id for fact, _ in automated_fills)),
                evidence=tuple(sorted(fact.evidence_ref for fact, _ in automated_fills)),
                missing=("Confirm that every automated RODI fill was normalized and classified.",),
                action="Verify automated-RODI inventory completeness before claiming safety.",
                evaluation_timestamp=evaluation_timestamp,
                evaluation_run_id=evaluation_run_id,
                policy_hash=policy_hash,
            )

        return self._result(
            graph=graph,
            state=InvariantState.PASS,
            summary="Every automated RODI fill has an independent high-high cutoff.",
            explanation=(
                "The complete automated-RODI inventory confirms independent final "
                "overflow protection for every fill."
            ),
            affected=tuple(sorted(fact.subject_id for fact, _ in automated_fills)),
            evidence=tuple(
                sorted(
                    {
                        *(fact.evidence_ref for fact, _ in automated_fills),
                        *inventory_evidence,
                    }
                )
            ),
            missing=(),
            action="No immediate action. Re-verify after RODI control changes.",
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

    @classmethod
    def _automated_fills(
        cls,
        graph: ReliabilityGraph,
    ) -> tuple[tuple[GraphFact, dict[str, JsonValue]], ...]:
        fills: list[tuple[GraphFact, dict[str, JsonValue]]] = []
        for fact in graph.facts:
            if (
                cls._property_is_true(fact, "automated_rodi")
                and cls._property_is_true(fact, "active")
                and isinstance(fact.value, dict)
            ):
                fills.append((fact, fact.value))
        return tuple(fills)

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
        return """RP-WATER-002 v1 — Automated RODI requires a high-high cutoff

Protects:
  The building and living system from an automated RODI fill overflowing after
  its normal high-level control fails.

Required evidence:
  Complete automated-RODI inventory and physical confirmation of an independent
  final high-high cutoff for every fill.

PASS:
  Every automated fill has a confirmed independent high-high cutoff.

FAIL:
  An automated fill is confirmed to have no independent high-high cutoff.

UNKNOWN:
  Cutoff confirmation or automated-fill inventory evidence is missing.

Operator action:
  Verify each physical cutoff and install one where confirmed absent.

Source:
  src/reefproof/invariants/water.py
Tests:
  tests/unit/test_rodi_invariant.py"""
