"""Backend-authored logical trees for the exact executable v0.1 rule catalog."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from reefproof.invariants import registered_invariant_definitions
from reefproof.invariants.models import Severity
from reefproof.invariants.registry import InvariantDefinition


class LogicalTreeNode(BaseModel):
    """One bounded presentation node, not a general-purpose expression."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rule", "all", "evidence", "outcome"]
    label: str
    state: Literal["PASS", "FAIL", "UNKNOWN"] | None = None
    children: tuple[LogicalTreeNode, ...] = ()


class InvariantTemplate(BaseModel):
    """One executable invariant represented for template-first browsing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant_id: str
    version: str
    title: str
    severity: Severity
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    evidence_requirements: tuple[str, ...]
    logical_tree: LogicalTreeNode


class InvariantCatalog(BaseModel):
    """The exact, backend-authoritative v0.1 template catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    templates: tuple[InvariantTemplate, ...]


def invariant_catalog() -> InvariantCatalog:
    templates = tuple(
        _template_from_definition(definition)
        for definition in sorted(
            registered_invariant_definitions(),
            key=lambda item: item.invariant_id,
        )
    )
    return InvariantCatalog(templates=templates)


def _template_from_definition(definition: InvariantDefinition) -> InvariantTemplate:
    invariant_id = definition.invariant_id
    version = definition.version
    title = definition.title
    severity = definition.severity
    explanation = definition.explain()
    evidence = (_section(explanation, "Required evidence"),)
    outcomes = tuple(
        LogicalTreeNode(
            kind="outcome",
            state=state,
            label=_section(explanation, state),
        )
        for state in ("PASS", "FAIL", "UNKNOWN")
    )
    tree = LogicalTreeNode(
        kind="rule",
        label=title,
        children=(
            LogicalTreeNode(
                kind="all",
                label="Required evidence",
                children=tuple(
                    LogicalTreeNode(kind="evidence", label=requirement) for requirement in evidence
                ),
            ),
            *outcomes,
        ),
    )
    return InvariantTemplate(
        invariant_id=invariant_id,
        version=version,
        title=title,
        severity=severity,
        evidence_requirements=evidence,
        logical_tree=tree,
    )


def _section(document: str, heading: str) -> str:
    lines = document.splitlines()
    marker = f"{heading}:"
    try:
        start = lines.index(marker) + 1
    except ValueError as error:
        raise ValueError(f"invariant explanation is missing {marker}") from error
    collected: list[str] = []
    for line in lines[start:]:
        if line in {"Protects:", "Required evidence:", "PASS:", "FAIL:", "UNKNOWN:"}:
            break
        if not line.strip() and collected:
            break
        if line.strip():
            collected.append(line.strip())
    text = " ".join(collected)
    if not text:
        raise ValueError(f"invariant explanation has an empty {marker} section")
    return text
