from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T13:00:00-04:00")
RUN_ID = "32345678-1234-4234-8234-123456789abc"
MODE_ID = "RP.MODE.0123456789abcdef"
EVIDENCE_ID = "RP.ANNOTATION.0123456789abcdef"


def _graph_with_service_mode(properties: dict[str, JsonValue]) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    return graph.model_copy(
        update={
            "nodes": (
                *graph.nodes,
                GraphNode(
                    node_id=MODE_ID,
                    display_name="Feed Service",
                    entity_type=EntityType.MODE,
                    provenance="AUTHORED",
                ),
            ),
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=MODE_ID,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={
                        "service_mode": True,
                        "service_mode_inventory_complete": True,
                        **properties,
                    },
                    provenance="AUTHORED",
                    evidence_ref=EVIDENCE_ID,
                ),
            ),
        }
    )


def _evaluate(graph: ReliabilityGraph):
    run = evaluate_graph(
        graph,
        evaluation_timestamp=TIMESTAMP,
        evaluation_run_id=RUN_ID,
    )
    return next(result for result in run.results if result.invariant_id == "RP-MODE-001")


def test_rp_mode_001_fails_for_indefinite_timeout() -> None:
    result = _evaluate(_graph_with_service_mode({"timeout_seconds": 0}))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (MODE_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert result.missing_evidence == ()
    assert "Feed Service" in result.detailed_explanation


def test_rp_mode_001_passes_for_finite_timeout() -> None:
    result = _evaluate(_graph_with_service_mode({"timeout_seconds": 900}))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (MODE_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert result.missing_evidence == ()


def test_rp_mode_001_is_unknown_when_timeout_is_missing() -> None:
    result = _evaluate(_graph_with_service_mode({}))

    assert result.state is InvariantState.UNKNOWN
    assert result.affected_entities == (MODE_ID,)
    assert result.missing_evidence == ("Finite timeout for Feed Service.",)


def test_rp_mode_001_is_unknown_when_service_mode_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every service mode was normalized and classified.",
    )
