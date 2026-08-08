from __future__ import annotations

from pathlib import Path

from reefproof.configuration import RelationshipType, load_fixture, snapshot_fixture
from reefproof.reliability import (
    GraphEdge,
    ReliabilityGraph,
    build_graph,
    dependency_cycles,
    find_correlated_redundancy,
    render_graph,
)

CORRELATED = Path("tests/fixtures/configuration/unsafe-correlated-returns.json")


def test_builds_typed_graph_with_provenance_and_evidence() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(CORRELATED)))

    assert [node.provenance for node in graph.nodes].count("OBSERVED") == 2
    assert [node.provenance for node in graph.nodes].count("AUTHORED") == 1
    assert len(graph.edges) == 3
    assert all(edge.provenance == "AUTHORED" for edge in graph.edges)
    assert all(edge.evidence_ref.startswith("RP.ANNOTATION.") for edge in graph.edges)


def test_graph_rendering_is_deterministic() -> None:
    snapshot = snapshot_fixture(load_fixture(CORRELATED))

    assert render_graph(build_graph(snapshot)) == render_graph(build_graph(snapshot))


def test_finds_redundant_returns_sharing_power_domain() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(CORRELATED)))
    names = {node.node_id: node.display_name for node in graph.nodes}

    correlations = find_correlated_redundancy(graph)

    assert len(correlations) == 1
    result = correlations[0]
    assert {names[result.first_id], names[result.second_id]} == {"Return A", "Return B"}
    assert names[result.failure_domain_id] == "Example Shared Power Domain"
    assert len(result.evidence_refs) == 3


def test_missing_power_relationship_is_not_guessed() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(CORRELATED)))
    without_power = graph.model_copy(
        update={
            "edges": tuple(
                edge for edge in graph.edges if edge.source_id != graph.edges[0].source_id
            )
        }
    )

    assert find_correlated_redundancy(without_power) == ()


def test_dependency_cycles_are_deterministic() -> None:
    graph = build_graph(snapshot_fixture(load_fixture(CORRELATED)))
    returns = sorted(
        node.node_id for node in graph.nodes if node.display_name in {"Return A", "Return B"}
    )
    cyclic = ReliabilityGraph(
        configuration_hash=graph.configuration_hash,
        annotation_hash=graph.annotation_hash,
        nodes=graph.nodes,
        edges=(
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
        ),
        facts=(),
    )

    assert dependency_cycles(cyclic) == ((returns[0], returns[1]),)
