from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reefproof.configuration import RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphEdge, GraphFact, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T12:30:00-04:00")
RUN_ID = "22345678-1234-4234-8234-123456789abc"


def _evaluate(graph):
    run = evaluate_graph(
        graph,
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in run.results if result.invariant_id == "RP-LOGIC-001")


def test_rp_logic_001_fails_for_dependency_cycle() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    returns = sorted(
        node.node_id for node in graph.nodes if node.display_name in {"Return A", "Return B"}
    )
    cyclic = graph.model_copy(
        update={
            "edges": (
                *graph.edges,
                GraphEdge(
                    source_id=returns[0],
                    target_id=returns[1],
                    relationship=RelationshipType.DEPENDS_ON,
                    provenance="AUTHORED",
                    evidence_ref=graph.edges[0].evidence_ref,
                ),
                GraphEdge(
                    source_id=returns[1],
                    target_id=returns[0],
                    relationship=RelationshipType.DEPENDS_ON,
                    provenance="AUTHORED",
                    evidence_ref=graph.edges[1].evidence_ref,
                ),
            )
        }
    )

    result = _evaluate(cyclic)

    assert result.state is InvariantState.FAIL
    assert "Return A" in result.detailed_explanation
    assert "Return B" in result.detailed_explanation
    assert len(result.evidence) == 2
    assert result.missing_evidence == ()


def test_rp_logic_001_passes_with_complete_acyclic_map() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    complete = graph.model_copy(
        update={
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=graph.nodes[0].node_id,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={"dependency_map_complete": True},
                    provenance="AUTHORED",
                    evidence_ref=graph.edges[0].evidence_ref,
                ),
            )
        }
    )

    result = _evaluate(complete)

    assert result.state is InvariantState.PASS
    assert result.evidence
    assert result.missing_evidence == ()


def test_rp_logic_001_is_unknown_without_completeness_evidence() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that all dependency and combiner relationships were normalized.",
    )
