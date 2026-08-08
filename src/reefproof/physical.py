"""Typed, explicitly mocked physical model for the v0.1 digital twin."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PhysicalSize(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    width_inches: float = Field(gt=0)
    height_inches: float = Field(gt=0)
    depth_inches: float = Field(gt=0)
    volume_gallons: float | None = Field(default=None, gt=0)


class DiagramGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: int = Field(ge=0, le=800)
    y: int = Field(ge=0, le=500)
    width: int = Field(gt=0, le=800)
    height: int = Field(gt=0, le=500)


class PhysicalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    physical_type: Literal["display_tank", "sump", "return_pump"]
    label: str
    quantity: int = Field(gt=0)
    elevation_inches: float = Field(ge=0)
    size: PhysicalSize
    geometry: DiagramGeometry


class PhysicalRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    target_id: str
    relationship_type: Literal["drains_to", "feeds", "returns_to"]
    direction: Literal["down", "left", "up_and_right"]
    dependency: str
    label: str
    svg_path: str = Field(pattern=r"^M [0-9 ]+(?: L [0-9 ]+)+$")


class MockFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str
    severity: Literal["critical", "high", "warning", "info"]
    icon: Literal["⚠", "▲", "●"]
    state_text: Literal["CRITICAL", "WARNING", "INFO"]
    summary: str
    affected_entity_ids: tuple[str, ...]


class PhysicalTwin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    coordinate_system: Literal["mock diagram units"] = "mock diagram units"
    entities: tuple[PhysicalEntity, ...]
    relationships: tuple[PhysicalRelationship, ...]
    findings: tuple[MockFinding, ...]

    @model_validator(mode="after")
    def relationships_and_findings_reference_known_entities(self) -> PhysicalTwin:
        entity_ids = {entity.entity_id for entity in self.entities}
        for relationship in self.relationships:
            if relationship.source_id not in entity_ids or relationship.target_id not in entity_ids:
                raise ValueError("physical relationship references an unknown entity")
        for finding in self.findings:
            if not set(finding.affected_entity_ids) <= entity_ids:
                raise ValueError("mock finding references an unknown entity")
        return self


def mock_collective_physical_twin() -> PhysicalTwin:
    """Return one deterministic authored model; no geometry is device-observed."""

    return PhysicalTwin(
        entities=(
            PhysicalEntity(
                entity_id="display_tank",
                physical_type="display_tank",
                label="Display tank",
                quantity=1,
                elevation_inches=48,
                size=PhysicalSize(
                    width_inches=48,
                    height_inches=24,
                    depth_inches=24,
                    volume_gallons=120,
                ),
                geometry=DiagramGeometry(x=330, y=35, width=260, height=145),
            ),
            PhysicalEntity(
                entity_id="sump",
                physical_type="sump",
                label="Sump",
                quantity=1,
                elevation_inches=0,
                size=PhysicalSize(
                    width_inches=36,
                    height_inches=18,
                    depth_inches=18,
                    volume_gallons=40,
                ),
                geometry=DiagramGeometry(x=330, y=310, width=260, height=105),
            ),
            PhysicalEntity(
                entity_id="return_pump",
                physical_type="return_pump",
                label="Return pump",
                quantity=1,
                elevation_inches=4,
                size=PhysicalSize(
                    width_inches=8,
                    height_inches=6,
                    depth_inches=5,
                ),
                geometry=DiagramGeometry(x=75, y=320, width=135, height=80),
            ),
        ),
        relationships=(
            PhysicalRelationship(
                source_id="display_tank",
                target_id="sump",
                relationship_type="drains_to",
                direction="down",
                dependency="Gravity drain path is present in this authored mock.",
                label="Mock drain: display tank down to sump",
                svg_path="M 570 180 L 570 310",
            ),
            PhysicalRelationship(
                source_id="sump",
                target_id="return_pump",
                relationship_type="feeds",
                direction="left",
                dependency="Return pump intake depends on authored sump water availability.",
                label="Mock feed: sump left to return pump",
                svg_path="M 330 365 L 210 365",
            ),
            PhysicalRelationship(
                source_id="return_pump",
                target_id="display_tank",
                relationship_type="returns_to",
                direction="up_and_right",
                dependency="Display return flow depends on the authored return pump path.",
                label="Mock return: pump up and right to display tank",
                svg_path="M 145 320 L 145 105 L 330 105",
            ),
        ),
        findings=(
            MockFinding(
                finding_id="mock-return-critical",
                severity="critical",
                icon="⚠",
                state_text="CRITICAL",
                summary="Mock example: return circulation is below the authored target.",
                affected_entity_ids=("return_pump", "display_tank"),
            ),
            MockFinding(
                finding_id="mock-sump-warning",
                severity="warning",
                icon="▲",
                state_text="WARNING",
                summary="Mock example: sump evidence needs operator review.",
                affected_entity_ids=("sump",),
            ),
            MockFinding(
                finding_id="mock-model-info",
                severity="info",
                icon="●",
                state_text="INFO",
                summary="All geometry and relationships are manually authored examples.",
                affected_entity_ids=("display_tank", "sump", "return_pump"),
            ),
        ),
    )
