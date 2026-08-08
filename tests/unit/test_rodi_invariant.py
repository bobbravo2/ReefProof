from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T15:30:00-04:00")
RUN_ID = "82345678-1234-4234-8234-123456789abc"
RODI_ID = "RP.DEVICE.9123456789abcdef"
EVIDENCE_ID = "RP.ANNOTATION.9123456789abcdef"


def _rodi_graph(properties: dict[str, JsonValue]) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    return graph.model_copy(
        update={
            "nodes": (
                *graph.nodes,
                GraphNode(
                    node_id=RODI_ID,
                    display_name="RODI Batch Fill",
                    entity_type=EntityType.DEVICE,
                    provenance="AUTHORED",
                ),
            ),
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=RODI_ID,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={
                        "automated_rodi": True,
                        "active": True,
                        "automated_rodi_inventory_complete": True,
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
    return next(result for result in run.results if result.invariant_id == "RP-WATER-002")


def test_rp_water_002_fails_when_high_high_cutoff_is_confirmed_absent() -> None:
    result = _evaluate(_rodi_graph({"independent_high_high_cutoff": False}))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (RODI_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert "RODI Batch Fill" in result.detailed_explanation


def test_rp_water_002_passes_with_independent_high_high_cutoff() -> None:
    result = _evaluate(_rodi_graph({"independent_high_high_cutoff": True}))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (RODI_ID,)
    assert result.evidence == (EVIDENCE_ID,)


def test_rp_water_002_is_unknown_when_cutoff_evidence_is_missing() -> None:
    result = _evaluate(_rodi_graph({}))

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == ("Independent high-high cutoff for RODI Batch Fill.",)


def test_rp_water_002_is_unknown_when_rodi_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every automated RODI fill was normalized and classified.",
    )
