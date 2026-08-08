from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphEdge, GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T17:30:00-04:00")
RUN_ID = "c2345678-1234-4234-8234-123456789abc"
MODE_ID = "RP.MODE.123456789abcdeff"
CIRCULATION_ID = "RP.DEVICE.123456789abcdeff"
MODE_EVIDENCE = "RP.ANNOTATION.123456789abcdeff"
CIRCULATION_EVIDENCE = "RP.ANNOTATION.223456789abcdeff"
MEMBERSHIP_EVIDENCE = "RP.ANNOTATION.323456789abcdeff"


def _operating_mode_graph(*, with_surviving_path: bool) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    nodes = (
        *graph.nodes,
        GraphNode(
            node_id=MODE_ID,
            display_name="Normal Operation",
            entity_type=EntityType.MODE,
            provenance="AUTHORED",
        ),
    )
    facts = (
        *graph.facts,
        GraphFact(
            subject_id=MODE_ID,
            relationship=RelationshipType.HAS_PROPERTY,
            value={
                "evaluated_operating_mode": True,
                "operating_mode_inventory_complete": True,
                "mode_membership_complete": True,
                "circulation_function_inventory_complete": True,
            },
            provenance="AUTHORED",
            evidence_ref=MODE_EVIDENCE,
        ),
    )
    edges = graph.edges
    if with_surviving_path:
        nodes = (
            *nodes,
            GraphNode(
                node_id=CIRCULATION_ID,
                display_name="Display Return",
                entity_type=EntityType.DEVICE,
                provenance="AUTHORED",
            ),
        )
        facts = (
            *facts,
            GraphFact(
                subject_id=CIRCULATION_ID,
                relationship=RelationshipType.HAS_PROPERTY,
                value={"approved_circulation_or_oxygenation": True},
                provenance="AUTHORED",
                evidence_ref=CIRCULATION_EVIDENCE,
            ),
        )
        edges = (
            *edges,
            GraphEdge(
                source_id=CIRCULATION_ID,
                target_id=MODE_ID,
                relationship=RelationshipType.ACTIVE_IN,
                provenance="AUTHORED",
                evidence_ref=MEMBERSHIP_EVIDENCE,
            ),
        )
    return graph.model_copy(update={"nodes": nodes, "facts": facts, "edges": edges})


def _evaluate(graph: ReliabilityGraph):
    run = evaluate_graph(
        graph,
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in run.results if result.invariant_id == "RP-CIRC-002")


def test_rp_circ_002_fails_when_mode_has_no_surviving_path() -> None:
    result = _evaluate(_operating_mode_graph(with_surviving_path=False))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (MODE_ID,)
    assert result.evidence == (MODE_EVIDENCE,)
    assert "Normal Operation" in result.detailed_explanation


def test_rp_circ_002_passes_when_each_mode_has_a_surviving_path() -> None:
    result = _evaluate(_operating_mode_graph(with_surviving_path=True))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == tuple(sorted((MODE_ID, CIRCULATION_ID)))
    assert set(result.evidence) == {
        MODE_EVIDENCE,
        CIRCULATION_EVIDENCE,
        MEMBERSHIP_EVIDENCE,
    }


def test_rp_circ_002_is_unknown_when_mode_evidence_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm operating modes, memberships, and approved circulation inventory.",
    )
