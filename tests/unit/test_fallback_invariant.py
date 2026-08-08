from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import JsonValue

from reefproof.configuration import EntityType, RelationshipType, load_fixture, snapshot_fixture
from reefproof.invariants import InvariantState, evaluate_graph
from reefproof.reliability import GraphFact, GraphNode, ReliabilityGraph, build_graph

FIXTURE = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")
TIMESTAMP = datetime.fromisoformat("2026-07-25T16:00:00-04:00")
RUN_ID = "92345678-1234-4234-8234-123456789abc"
OUTPUT_ID = "RP.OUTPUT.a123456789abcdef"
EVIDENCE_ID = "RP.ANNOTATION.a123456789abcdef"


def _critical_output_graph(properties: dict[str, JsonValue]) -> ReliabilityGraph:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))
    return graph.model_copy(
        update={
            "nodes": (
                *graph.nodes,
                GraphNode(
                    node_id=OUTPUT_ID,
                    display_name="Frag Exchange Pump",
                    entity_type=EntityType.OUTPUT,
                    provenance="AUTHORED",
                ),
            ),
            "facts": (
                *graph.facts,
                GraphFact(
                    subject_id=OUTPUT_ID,
                    relationship=RelationshipType.HAS_PROPERTY,
                    value={
                        "critical_output": True,
                        "critical_output_inventory_complete": True,
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
    return next(result for result in run.results if result.invariant_id == "RP-FALLBACK-001")


def test_rp_fallback_001_fails_when_known_fallback_is_assessed_unsafe() -> None:
    result = _evaluate(
        _critical_output_graph(
            {
                "unavailable_input_behavior": "remain_on",
                "unavailable_input_fallback_safe": False,
            }
        )
    )

    assert result.state is InvariantState.FAIL
    assert result.affected_entities == (OUTPUT_ID,)
    assert result.evidence == (EVIDENCE_ID,)
    assert "Frag Exchange Pump" in result.detailed_explanation


def test_rp_fallback_001_passes_when_known_fallback_is_assessed_safe() -> None:
    result = _evaluate(
        _critical_output_graph(
            {
                "unavailable_input_behavior": "turn_off",
                "unavailable_input_fallback_safe": True,
            }
        )
    )

    assert result.state is InvariantState.PASS
    assert result.affected_entities == (OUTPUT_ID,)
    assert result.evidence == (EVIDENCE_ID,)


def test_rp_fallback_001_is_unknown_when_behavior_is_missing() -> None:
    result = _evaluate(_critical_output_graph({}))

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Unavailable-input behavior for Frag Exchange Pump.",
        "Safety assessment of unavailable-input fallback for Frag Exchange Pump.",
    )


def test_rp_fallback_001_is_unknown_when_critical_output_inventory_is_incomplete() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(FIXTURE)))

    result = _evaluate(graph)

    assert result.state is InvariantState.UNKNOWN
    assert result.missing_evidence == (
        "Confirm that every critical output was normalized and classified.",
    )
