from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphEdge, GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T17:00:00-04:00")
RUN_ID = "b2345678-1234-4234-8234-123456789abc"
HEATER_A = "RP.DEVICE.e123456789abcdef"
HEATER_B = "RP.DEVICE.f123456789abcdef"
POWER_A = "RP.POWER_DOMAIN.e123456789abcdef"
POWER_B = "RP.POWER_DOMAIN.f123456789abcdef"
CONTROLLER_A = "RP.CONTROLLER.e123456789abcdef"
CONTROLLER_B = "RP.CONTROLLER.f123456789abcdef"
SENSOR_A = "RP.SENSOR.e123456789abcdef"
SENSOR_B = "RP.SENSOR.f123456789abcdef"


def _heater_graph(*, shared_power: bool, complete: bool = True) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    power_b = POWER_A if shared_power else POWER_B
    nodes = (
        *graph.nodes,
        GraphNode(
            node_id=HEATER_A,
            display_name="Primary Heater",
            entity_type=EntityType.DEVICE,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=HEATER_B,
            display_name="Secondary Heater",
            entity_type=EntityType.DEVICE,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=POWER_A,
            display_name="Heater Power A",
            entity_type=EntityType.POWER_DOMAIN,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=CONTROLLER_A,
            display_name="Controller A",
            entity_type=EntityType.CONTROLLER,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=CONTROLLER_B,
            display_name="Controller B",
            entity_type=EntityType.CONTROLLER,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=SENSOR_A,
            display_name="Temperature A",
            entity_type=EntityType.SENSOR,
            provenance="AUTHORED",
        ),
        GraphNode(
            node_id=SENSOR_B,
            display_name="Temperature B",
            entity_type=EntityType.SENSOR,
            provenance="AUTHORED",
        ),
    )
    if not shared_power:
        nodes = (
            *nodes,
            GraphNode(
                node_id=POWER_B,
                display_name="Heater Power B",
                entity_type=EntityType.POWER_DOMAIN,
                provenance="AUTHORED",
            ),
        )
    facts = (
        *graph.facts,
        GraphFact(
            subject_id=HEATER_A,
            relationship=RelationshipType.HAS_PROPERTY,
            value={
                "heater": True,
                "active": True,
                "heater_redundancy_group": "display",
                "redundant_heater_inventory_complete": complete,
                "heater_failure_domain_map_complete": complete,
            },
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.e123456789abcdef",
        ),
        GraphFact(
            subject_id=HEATER_B,
            relationship=RelationshipType.HAS_PROPERTY,
            value={
                "heater": True,
                "active": True,
                "heater_redundancy_group": "display",
            },
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.f123456789abcdef",
        ),
    )
    edges = (
        *graph.edges,
        GraphEdge(
            source_id=HEATER_A,
            target_id=POWER_A,
            relationship=RelationshipType.POWERED_BY,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0111111111111111",
        ),
        GraphEdge(
            source_id=HEATER_B,
            target_id=power_b,
            relationship=RelationshipType.POWERED_BY,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0222222222222222",
        ),
        GraphEdge(
            source_id=HEATER_A,
            target_id=CONTROLLER_A,
            relationship=RelationshipType.CONTROLLED_BY,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0333333333333333",
        ),
        GraphEdge(
            source_id=HEATER_B,
            target_id=CONTROLLER_B,
            relationship=RelationshipType.CONTROLLED_BY,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0444444444444444",
        ),
        GraphEdge(
            source_id=HEATER_A,
            target_id=SENSOR_A,
            relationship=RelationshipType.DEPENDS_ON,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0555555555555555",
        ),
        GraphEdge(
            source_id=HEATER_B,
            target_id=SENSOR_B,
            relationship=RelationshipType.DEPENDS_ON,
            provenance="AUTHORED",
            evidence_ref="RP.ANNOTATION.0666666666666666",
        ),
    )
    return graph.model_copy(update={"nodes": nodes, "facts": facts, "edges": edges})


def _evaluate(graph: ReliabilityGraph):
    run = evaluate_graph(
        graph,
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in run.results if result.invariant_id == "RP-HEAT-001")


def test_rp_heat_001_fails_when_redundant_heaters_share_power() -> None:
    result = _evaluate(_heater_graph(shared_power=True))

    assert result.state is InvariantState.FAIL
    assert set(result.affected_entities) == {HEATER_A, HEATER_B, POWER_A}
    assert "Heater Power A" in result.detailed_explanation
    assert result.missing_evidence == ()


def test_rp_heat_001_passes_with_independent_failure_domains() -> None:
    result = _evaluate(_heater_graph(shared_power=False))

    assert result.state is InvariantState.PASS
    assert {HEATER_A, HEATER_B}.issubset(result.affected_entities)
    assert result.evidence
    assert result.missing_evidence == ()


def test_rp_heat_001_is_unknown_when_failure_domain_map_is_incomplete() -> None:
    result = _evaluate(_heater_graph(shared_power=False, complete=False))

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm redundant-heater inventory and complete failure-domain mapping.",
    )
