from __future__ import annotations

import json

from reefproof.information_architecture import (
    PROJECT_ROUTE,
    OverviewSection,
    SystemMapLayer,
    project_information_architecture,
)


def test_navigation_has_the_exact_accepted_hierarchy_and_order() -> None:
    architecture = project_information_architecture()

    assert architecture.project_name == "Primary Reef System"
    assert [item.label for item in architecture.primary_navigation] == [
        "Overview",
        "System Map",
        "Assurance",
        "Evidence",
        "Sessions",
    ]

    assurance = architecture.primary_navigation[2]
    assert [item.label for item in assurance.children] == [
        "Findings",
        "Unknowns",
        "Rules",
        "Decisions",
        "Assumptions",
    ]

    sessions = architecture.primary_navigation[4]
    assert [item.label for item in sessions.children] == [
        "Continue interview",
        "Candidate review queue",
        "History",
    ]
    assert all(not item.children for item in assurance.children + sessions.children)


def test_overview_and_system_map_have_exact_deterministic_order() -> None:
    architecture = project_information_architecture()

    assert architecture.overview_sections == (
        OverviewSection.RECOMMENDED_NEXT_ACTION,
        OverviewSection.CURRENT_POSTURE,
        OverviewSection.HIGHEST_CONSEQUENCE_RISKS,
        OverviewSection.IMPORTANT_UNKNOWNS,
        OverviewSection.RECENT_ACCEPTED_DECISIONS,
        OverviewSection.COMPACT_SYSTEM_MAP,
        OverviewSection.CONTINUE_INTERVIEW,
    )
    assert architecture.system_map_layers == (
        SystemMapLayer.PHYSICAL_LAYOUT,
        SystemMapLayer.WATER_FLOW,
        SystemMapLayer.POWER,
        SystemMapLayer.CONTROL,
        SystemMapLayer.DEPENDENCIES,
        SystemMapLayer.EVIDENCE_STATUS,
        SystemMapLayer.FINDINGS,
    )


def test_routes_are_stable_unique_and_do_not_invent_equipment_detail() -> None:
    architecture = project_information_architecture()
    entries = [
        item for primary in architecture.primary_navigation for item in (primary, *primary.children)
    ]
    routes = [item.route for item in entries]

    assert architecture.project_route == PROJECT_ROUTE
    assert routes == [
        f"{PROJECT_ROUTE}/overview",
        f"{PROJECT_ROUTE}/system-map",
        f"{PROJECT_ROUTE}/assurance",
        f"{PROJECT_ROUTE}/assurance/findings",
        f"{PROJECT_ROUTE}/assurance/unknowns",
        f"{PROJECT_ROUTE}/assurance/rules",
        f"{PROJECT_ROUTE}/assurance/decisions",
        f"{PROJECT_ROUTE}/assurance/assumptions",
        f"{PROJECT_ROUTE}/evidence",
        f"{PROJECT_ROUTE}/sessions",
        f"{PROJECT_ROUTE}/sessions/continue-interview",
        f"{PROJECT_ROUTE}/sessions/candidate-review-queue",
        f"{PROJECT_ROUTE}/sessions/history",
    ]
    assert len(routes) == len(set(routes))
    assert architecture.action_detail_route_template == f"{PROJECT_ROUTE}/actions/{{action_id}}"
    assert all("equipment" not in route for route in routes)


def test_conversation_is_not_a_primary_area_or_generic_chat_center() -> None:
    architecture = project_information_architecture()
    primary_labels = {item.label.casefold() for item in architecture.primary_navigation}
    primary_routes = {item.route.casefold() for item in architecture.primary_navigation}

    assert "conversation" not in primary_labels
    assert "chat" not in primary_labels
    assert all("conversation" not in route and "chat" not in route for route in primary_routes)


def test_contract_serialization_is_repeatable_without_an_llm() -> None:
    first = project_information_architecture()
    second = project_information_architecture()

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert json.loads(first.model_dump_json()) == first.model_dump(mode="json")
