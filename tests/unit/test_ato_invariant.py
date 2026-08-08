from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T15:00:00-04:00")
RUN_ID = "72345678-1234-4234-8234-123456789abc"
ATO_ID = "RP.DEVICE.8123456789abcdef"
EVIDENCE_ID = "RP.ANNOTATION.8123456789abcdef"


def _ato_graph(properties: dict[str, JsonValue]) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    return graph.model_copy(
        update={
            "nodes": (
                *graph.nodes,
                GraphNode(
                    node_id=ATO_ID,
                    display_name="Display ATO",
                    entity_type=EntityType.DEVICE,
                    provenance="AUTHORED",
                ),
            ),
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=ATO_ID,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={
                        "ato": True,
                        "active": True,
                        "active_ato_inventory_complete": True,
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
    return next(result for result in run.results if result.invariant_id == "RP-WATER-001")


SAFE_PROPERTIES: dict[str, JsonValue] = {
    "maximum_runtime_seconds": 60,
    "pump_flow_liters_per_hour": 12.0,
    "high_water_inhibit": True,
    "independent_high_stop": True,
}


def test_rp_water_001_fails_when_ato_bound_is_confirmed_absent() -> None:
    properties = {**SAFE_PROPERTIES, "maximum_runtime_seconds": 0}

    result = _evaluate(_ato_graph(properties))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (ATO_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert "maximum runtime" in result.detailed_explanation


def test_rp_water_001_passes_when_ato_addition_is_bounded() -> None:
    result = _evaluate(_ato_graph(SAFE_PROPERTIES))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (ATO_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert result.missing_evidence == ()


def test_rp_water_001_is_unknown_when_evidence_is_missing() -> None:
    properties = dict(SAFE_PROPERTIES)
    del properties["pump_flow_liters_per_hour"]

    result = _evaluate(_ato_graph(properties))

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Pump flow or maximum-addition-volume evidence for Display ATO.",
    )


def test_rp_water_001_is_unknown_when_ato_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every active ATO path was normalized and classified.",
    )
