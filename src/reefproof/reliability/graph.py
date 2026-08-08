"""Deterministic typed reliability graph."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from reefproof.configuration import ConfigurationSnapshot, EntityType, RelationshipType


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    display_name: str
    entity_type: EntityType
    provenance: Literal["OBSERVED", "AUTHORED"]


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    target_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    relationship: RelationshipType
    provenance: Literal["AUTHORED"]
    evidence_ref: str = Field(pattern=r"^RP\.ANNOTATION\.[0-9a-f]{16}$")


class GraphFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    subject_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    relationship: RelationshipType
    value: JsonValue
    provenance: Literal["AUTHORED"]
    evidence_ref: str = Field(pattern=r"^RP\.ANNOTATION\.[0-9a-f]{16}$")


class ReliabilityGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    graph_version: Literal["0.1"] = "0.1"
    configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    annotation_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    facts: tuple[GraphFact, ...]


def build_graph(snapshot: ConfigurationSnapshot) -> ReliabilityGraph:
    """Build only relationships explicitly present in canonical evidence."""

    nodes = [
        GraphNode(
            node_id=entity.reefproof_id,
            display_name=entity.display_name,
            entity_type=entity.entity_type,
            provenance="OBSERVED",
        )
        for entity in snapshot.entities
    ]
    nodes.extend(
        GraphNode(
            node_id=entity.reefproof_id,
            display_name=entity.display_name,
            entity_type=entity.entity_type,
            provenance="AUTHORED",
        )
        for entity in snapshot.authored_entities
    )
    known_ids = {node.node_id for node in nodes}

    edges: list[GraphEdge] = []
    facts: list[GraphFact] = []
    for annotation in snapshot.annotations:
        if annotation.subject_id not in known_ids:
            raise ValueError(f"annotation subject missing from graph: {annotation.subject_id}")
        if annotation.target_id is not None:
            if annotation.target_id not in known_ids:
                raise ValueError(f"annotation target missing from graph: {annotation.target_id}")
            edges.append(
                GraphEdge(
                    source_id=annotation.subject_id,
                    target_id=annotation.target_id,
                    relationship=annotation.relationship,
                    provenance="AUTHORED",
                    evidence_ref=annotation.annotation_id,
                )
            )
        else:
            facts.append(
                GraphFact(
                    subject_id=annotation.subject_id,
                    relationship=annotation.relationship,
                    value=annotation.value,
                    provenance="AUTHORED",
                    evidence_ref=annotation.annotation_id,
                )
            )

    return ReliabilityGraph(
        configuration_hash=snapshot.configuration_hash,
        annotation_hash=snapshot.annotation_hash,
        nodes=tuple(sorted(nodes, key=lambda node: node.node_id)),
        edges=tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge.source_id,
                    edge.relationship.value,
                    edge.target_id,
                    edge.evidence_ref,
                ),
            )
        ),
        facts=tuple(
            sorted(
                facts,
                key=lambda fact: (
                    fact.subject_id,
                    fact.relationship.value,
                    fact.evidence_ref,
                ),
            )
        ),
    )


def render_graph(graph: ReliabilityGraph) -> str:
    document = graph.model_dump(mode="json")
    return f"{json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)}\n"


def summarize_graph(graph: ReliabilityGraph) -> str:
    observed = sum(node.provenance == "OBSERVED" for node in graph.nodes)
    authored = sum(node.provenance == "AUTHORED" for node in graph.nodes)
    return (
        f"Reliability graph: {len(graph.nodes)} node(s) "
        f"({observed} observed, {authored} authored), "
        f"{len(graph.edges)} relationship(s), {len(graph.facts)} value fact(s)."
    )
