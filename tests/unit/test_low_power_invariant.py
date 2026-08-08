from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphEdge, GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T16:30:00-04:00")
RUN_ID = "a2345678-1234-4234-8234-123456789abc"
MODE_ID = "RP.MODE.b123456789abcdef"
CIRCULATION_ID = "RP.DEVICE.b123456789abcdef"
MODE_EVIDENCE = "RP.ANNOTATION.b123456789abcdef"
CIRCULATION_EVIDENCE = "RP.ANNOTATION.c123456789abcdef"
MEMBERSHIP_EVIDENCE = "RP.ANNOTATION.d123456789abcdef"


def _low_power_graph(*, with_circulation: bool) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    nodes = (
        *graph.nodes,
        GraphNode(
            node_id=MODE_ID,
            display_name="Low Power",
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
                "low_power_mode": True,
                "low_power_mode_inventory_complete": True,
                "mode_membership_complete": True,
            },
            provenance="AUTHORED",
            evidence_ref=MODE_EVIDENCE,
        ),
    )
    edges = graph.edges
    if with_circulation:
        nodes = (
            *nodes,
            GraphNode(
                node_id=CIRCULATION_ID,
                display_name="Battery Wavemaker",
                entity_type=EntityType.DEVICE,
                provenance="AUTHORED",
            ),
        )
        facts = (
            *facts,
            GraphFact(
                subject_id=CIRCULATION_ID,
                relationship=RelationshipType.HAS_PROPERTY,
                value={"battery_approved_circulation": True},
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
    return next(result for result in run.results if result.invariant_id == "RP-CIRC-003")


def test_rp_circ_003_fails_when_low_power_has_no_useful_circulation() -> None:
    result = _evaluate(_low_power_graph(with_circulation=False))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (MODE_ID,)
    assert result.evidence == (MODE_EVIDENCE,)
    assert "Low Power" in result.detailed_explanation


def test_rp_circ_003_passes_with_battery_approved_circulation() -> None:
    result = _evaluate(_low_power_graph(with_circulation=True))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == tuple(sorted((MODE_ID, CIRCULATION_ID)))
    assert set(result.evidence) == {
        MODE_EVIDENCE,
        CIRCULATION_EVIDENCE,
        MEMBERSHIP_EVIDENCE,
    }


def test_rp_circ_003_is_unknown_when_low_power_evidence_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm the Low Power mode and its complete output membership.",
    )
