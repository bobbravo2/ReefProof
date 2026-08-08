"""Deterministic information architecture for the primary reef system."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reefproof.project_state import PROJECT_ID, PROJECT_NAME

PROJECT_ROUTE: Literal["/projects/primary-reef-system"] = "/projects/primary-reef-system"


class NavigationItem(BaseModel):
    """One stable, purpose-specific navigation destination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    route: str
    children: tuple[NavigationItem, ...] = ()


class OverviewSection(StrEnum):
    """Accepted top-to-bottom order for the project orientation surface."""

    RECOMMENDED_NEXT_ACTION = "recommended_next_action"
    CURRENT_POSTURE = "current_posture"
    HIGHEST_CONSEQUENCE_RISKS = "highest_consequence_risks"
    IMPORTANT_UNKNOWNS = "important_unknowns"
    RECENT_ACCEPTED_DECISIONS = "recent_accepted_decisions"
    COMPACT_SYSTEM_MAP = "compact_system_map"
    CONTINUE_INTERVIEW = "continue_interview"


class SystemMapLayer(StrEnum):
    """Presentational layers over canonical typed system state."""

    PHYSICAL_LAYOUT = "physical_layout"
    WATER_FLOW = "water_flow"
    POWER = "power"
    CONTROL = "control"
    DEPENDENCIES = "dependencies"
    EVIDENCE_STATUS = "evidence_status"
    FINDINGS = "findings"


class ProjectInformationArchitecture(BaseModel):
    """Complete v0.1 navigation and orientation contract for one project."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    project_id: Literal["primary-reef-system"] = PROJECT_ID
    project_name: str = PROJECT_NAME
    project_route: Literal["/projects/primary-reef-system"] = PROJECT_ROUTE
    primary_navigation: tuple[NavigationItem, ...]
    overview_sections: tuple[OverviewSection, ...]
    system_map_layers: tuple[SystemMapLayer, ...]
    action_detail_route_template: Literal["/projects/primary-reef-system/actions/{action_id}"] = (
        "/projects/primary-reef-system/actions/{action_id}"
    )


def project_information_architecture() -> ProjectInformationArchitecture:
    """Return the accepted information architecture without runtime or LLM input."""

    return ProjectInformationArchitecture(
        primary_navigation=(
            NavigationItem(label="Overview", route=f"{PROJECT_ROUTE}/overview"),
            NavigationItem(label="System Map", route=f"{PROJECT_ROUTE}/system-map"),
            NavigationItem(
                label="Assurance",
                route=f"{PROJECT_ROUTE}/assurance",
                children=(
                    NavigationItem(
                        label="Findings",
                        route=f"{PROJECT_ROUTE}/assurance/findings",
                    ),
                    NavigationItem(
                        label="Unknowns",
                        route=f"{PROJECT_ROUTE}/assurance/unknowns",
                    ),
                    NavigationItem(
                        label="Rules",
                        route=f"{PROJECT_ROUTE}/assurance/rules",
                    ),
                    NavigationItem(
                        label="Decisions",
                        route=f"{PROJECT_ROUTE}/assurance/decisions",
                    ),
                    NavigationItem(
                        label="Assumptions",
                        route=f"{PROJECT_ROUTE}/assurance/assumptions",
                    ),
                ),
            ),
            NavigationItem(label="Evidence", route=f"{PROJECT_ROUTE}/evidence"),
            NavigationItem(
                label="Sessions",
                route=f"{PROJECT_ROUTE}/sessions",
                children=(
                    NavigationItem(
                        label="Continue interview",
                        route=f"{PROJECT_ROUTE}/sessions/continue-interview",
                    ),
                    NavigationItem(
                        label="Candidate review queue",
                        route=f"{PROJECT_ROUTE}/sessions/candidate-review-queue",
                    ),
                    NavigationItem(
                        label="History",
                        route=f"{PROJECT_ROUTE}/sessions/history",
                    ),
                ),
            ),
        ),
        overview_sections=tuple(OverviewSection),
        system_map_layers=tuple(SystemMapLayer),
    )
