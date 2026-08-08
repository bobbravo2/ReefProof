"""Explicit graph-shape analysis without invariant policy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from reefproof.configuration import RelationshipType
from reefproof.reliability.graph import ReliabilityGraph


class CorrelatedRedundancy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    first_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    second_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    failure_domain_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    evidence_refs: tuple[str, ...]


def _targets(
    graph: ReliabilityGraph,
    subject_id: str,
    relationship: RelationshipType,
) -> dict[str, str]:
    return {
        edge.target_id: edge.evidence_ref
        for edge in graph.edges
        if edge.source_id == subject_id and edge.relationship is relationship
    }


def find_correlated_redundancy(
    graph: ReliabilityGraph,
) -> tuple[CorrelatedRedundancy, ...]:
    """Find explicitly redundant pairs sharing an explicit power domain."""

    results: list[CorrelatedRedundancy] = []
    seen_pairs: set[tuple[str, str]] = set()
    for edge in graph.edges:
        if edge.relationship is not RelationshipType.REDUNDANT_WITH:
            continue
        first_id, second_id = sorted((edge.source_id, edge.target_id))
        pair = (first_id, second_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        first_power = _targets(graph, first_id, RelationshipType.POWERED_BY)
        second_power = _targets(graph, second_id, RelationshipType.POWERED_BY)
        for failure_domain_id in sorted(first_power.keys() & second_power.keys()):
            results.append(
                CorrelatedRedundancy(
                    first_id=first_id,
                    second_id=second_id,
                    failure_domain_id=failure_domain_id,
                    evidence_refs=tuple(
                        sorted(
                            {
                                edge.evidence_ref,
                                first_power[failure_domain_id],
                                second_power[failure_domain_id],
                            }
                        )
                    ),
                )
            )
    return tuple(
        sorted(
            results,
            key=lambda result: (
                result.first_id,
                result.second_id,
                result.failure_domain_id,
            ),
        )
    )


def dependency_cycles(graph: ReliabilityGraph) -> tuple[tuple[str, ...], ...]:
    """Return deterministic simple cycles among explicit dependency edges."""

    adjacency: dict[str, set[str]] = {node.node_id: set() for node in graph.nodes}
    for edge in graph.edges:
        if edge.relationship is RelationshipType.DEPENDS_ON:
            adjacency[edge.source_id].add(edge.target_id)

    cycles: set[tuple[str, ...]] = set()

    def canonical_cycle(nodes: list[str]) -> tuple[str, ...]:
        cycle = nodes[:-1]
        rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
        return min(rotations)

    def visit(start: str, current: str, path: list[str], visited: set[str]) -> None:
        for target in sorted(adjacency[current]):
            if target == start:
                cycles.add(canonical_cycle([*path, target]))
            elif target not in visited:
                visit(start, target, [*path, target], {*visited, target})

    for node_id in sorted(adjacency):
        visit(node_id, node_id, [node_id], {node_id})

    return tuple(sorted(cycles))
