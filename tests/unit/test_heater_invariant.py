from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T13:30:00-04:00")
RUN_ID = "42345678-1234-4234-8234-123456789abc"
HEATER_ID = "RP.DEVICE.1123456789abcdef"
EVIDENCE_ID = "RP.ANNOTATION.1123456789abcdef"


def _graph_with_heater(properties: dict[str, JsonValue]) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    return graph.model_copy(
        update={
            "nodes": (
                *graph.nodes,
                GraphNode(
                    node_id=HEATER_ID,
                    display_name="Display Heater",
                    entity_type=EntityType.DEVICE,
                    provenance="AUTHORED",
                ),
            ),
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=HEATER_ID,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={
                        "heater": True,
                        "active": True,
                        "active_heater_inventory_complete": True,
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
    return next(result for result in run.results if result.invariant_id == "RP-HEAT-002")


def test_rp_heat_002_fails_when_safeguard_is_confirmed_absent() -> None:
    result = _evaluate(_graph_with_heater({"independent_safeguard": False}))

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (HEATER_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert result.missing_evidence == ()
    assert "Display Heater" in result.detailed_explanation


def test_rp_heat_002_passes_when_safeguard_is_confirmed() -> None:
    result = _evaluate(_graph_with_heater({"independent_safeguard": True}))

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (HEATER_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert result.missing_evidence == ()


def test_rp_heat_002_is_unknown_when_safeguard_evidence_is_missing() -> None:
    result = _evaluate(_graph_with_heater({}))

    assert result.state is InvariantState.UNKNOWN
    assert result.affected_entities == (HEATER_ID,)
    assert result.missing_evidence == (
        "Independent thermostat or high-limit safeguard for Display Heater.",
    )


def test_rp_heat_002_is_unknown_when_active_heater_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every active heater was normalized and classified.",
    )
