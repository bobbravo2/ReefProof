from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphEdge, GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T14:00:00-04:00")
RUN_ID = "52345678-1234-4234-8234-123456789abc"
UV_ID = "RP.DEVICE.2123456789abcdef"
FLOW_ID = "RP.SENSOR.2123456789abcdef"
UV_EVIDENCE = "RP.ANNOTATION.2123456789abcdef"
FLOW_EVIDENCE = "RP.ANNOTATION.3123456789abcdef"
DEPENDENCY_EVIDENCE = "RP.ANNOTATION.4123456789abcdef"


def _active_uv_graph(*, with_flow_permissive: bool) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    nodes = (
        *graph.nodes,
        GraphNode(
            node_id=UV_ID,
            display_name="Display UV",
            entity_type=EntityType.DEVICE,
            provenance="AUTHORED",
        ),
    )
    facts = (
        *graph.facts,
        GraphFact(
            subject_id=UV_ID,
            relationship=RelationshipType.HAS_PROPERTY,
            value={
                "uv": True,
                "active": True,
                "active_uv_inventory_complete": True,
                "dependency_map_complete": True,
            },
            provenance="AUTHORED",
            evidence_ref=UV_EVIDENCE,
        ),
    )
    edges = graph.edges
    if with_flow_permissive:
        nodes = (
            *nodes,
            GraphNode(
                node_id=FLOW_ID,
                display_name="UV Branch Flow",
                entity_type=EntityType.SENSOR,
                provenance="AUTHORED",
            ),
        )
        facts = (
            *facts,
            GraphFact(
                subject_id=FLOW_ID,
                relationship=RelationshipType.HAS_PROPERTY,
                value={"adequate_flow_permissive": True},
                provenance="AUTHORED",
                evidence_ref=FLOW_EVIDENCE,
            ),
        )
        edges = (
            *edges,
            GraphEdge(
                source_id=UV_ID,
                target_id=FLOW_ID,
                relationship=RelationshipType.DEPENDS_ON,
                provenance="AUTHORED",
                evidence_ref=DEPENDENCY_EVIDENCE,
            ),
        )
    return graph.model_copy(update={"nodes": nodes, "facts": facts, "edges": edges})


def _evaluate(graph: ReliabilityGraph):
    run = evaluate_graph(
        graph,
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in run.results if result.invariant_id == "RP-FLOW-001")


def test_rp_flow_001_fails_when_active_uv_has_no_flow_permissive() -> None:
    result = _evaluate(_active_uv_graph(with_flow_permissive=False))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (UV_ID,)
    assert result.evidence == (UV_EVIDENCE,)
    assert result.missing_evidence == ()
    assert "Display UV" in result.detailed_explanation


def test_rp_flow_001_passes_with_explicit_adequate_flow_dependency() -> None:
    result = _evaluate(_active_uv_graph(with_flow_permissive=True))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (UV_ID, FLOW_ID)
    assert set(result.evidence) == {UV_EVIDENCE, FLOW_EVIDENCE, DEPENDENCY_EVIDENCE}
    assert result.missing_evidence == ()


def test_rp_flow_001_is_unknown_when_active_uv_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every active UV load was normalized and classified.",
        "Confirm that every UV load dependency was normalized.",
    )
