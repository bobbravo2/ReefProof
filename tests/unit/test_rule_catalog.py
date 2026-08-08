from __future__ import annotations

from reefproof.invariants import (
    registered_invariant_definitions,
    registered_invariant_ids,
)
from reefproof.rules import invariant_catalog


def test_catalog_contains_all_and_only_executable_v01_invariants() -> None:
    catalog = invariant_catalog()

    assert len(catalog.templates) == 15
    assert {template.invariant_id for template in catalog.templates} == set(
        registered_invariant_ids()
    )
    assert len({template.invariant_id for template in catalog.templates}) == len(catalog.templates)
    assert [template.invariant_id for template in catalog.templates] == sorted(
        registered_invariant_ids()
    )


def test_catalog_metadata_and_tree_derive_from_executable_definitions() -> None:
    catalog = invariant_catalog()
    definitions = {
        definition.invariant_id: definition for definition in registered_invariant_definitions()
    }

    for template in catalog.templates:
        definition = definitions[template.invariant_id]
        assert template.version == definition.version
        assert template.title == definition.title
        assert template.severity == definition.severity
        assert template.collective_name == "Mock Collective"
        assert template.provenance_label == "MANUAL / NOT LIVE"
        assert template.live_observation is False
        assert template.evidence_requirements
        assert template.logical_tree.kind == "rule"
        evidence_group, *outcomes = template.logical_tree.children
        assert evidence_group.kind == "all"
        assert evidence_group.children
        assert {outcome.state for outcome in outcomes} == {
            "PASS",
            "FAIL",
            "UNKNOWN",
        }
        assert all(outcome.kind == "outcome" and outcome.label for outcome in outcomes)
