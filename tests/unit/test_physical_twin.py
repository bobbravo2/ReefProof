from __future__ import annotations

import pytest
from pydantic import ValidationError

from reefproof.physical import PhysicalTwin, mock_collective_physical_twin


def test_mock_physical_twin_is_complete_deterministic_and_manual() -> None:
    twin = mock_collective_physical_twin()

    assert twin == mock_collective_physical_twin()
    assert twin.collective_name == "Mock Collective"
    assert twin.provenance_label == "MANUAL / NOT LIVE"
    assert twin.live_observation is False
    assert {entity.physical_type for entity in twin.entities} == {
        "display_tank",
        "sump",
        "return_pump",
    }
    assert all(
        entity.quantity > 0
        and entity.elevation_inches >= 0
        and entity.size.width_inches > 0
        and entity.size.height_inches > 0
        and entity.size.depth_inches > 0
        for entity in twin.entities
    )
    assert {relationship.direction for relationship in twin.relationships} == {
        "down",
        "left",
        "up_and_right",
    }
    assert all(relationship.dependency for relationship in twin.relationships)
    assert {(finding.severity, finding.icon, finding.state_text) for finding in twin.findings} == {
        ("critical", "⚠", "CRITICAL"),
        ("warning", "▲", "WARNING"),
        ("info", "●", "INFO"),
    }


def test_physical_twin_rejects_unknown_relationship_entity() -> None:
    document = mock_collective_physical_twin().model_dump(mode="json")
    document["relationships"][0]["target_id"] = "invented_device"

    with pytest.raises(ValidationError, match="unknown entity"):
        PhysicalTwin.model_validate(document)
