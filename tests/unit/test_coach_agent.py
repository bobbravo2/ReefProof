from __future__ import annotations

import tomllib
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENT_DIRECTORY = ROOT / ".codex" / "agents"


class ExpectedAgent(NamedTuple):
    name: str
    requirements: tuple[str, ...]


AGENTS = {
    "reefproof-reviewer.toml": ExpectedAgent(
        name="reefproof_reviewer",
        requirements=(
            "goal",
            "acceptance criteria",
            "exact commit or diff",
            "changed paths",
            "focused test evidence",
            "accepted exceptions",
            "never expand scope",
            "never edit files",
            "external writes",
            "never approve",
            "deploy",
            "never infer missing evidence as pass",
        ),
    )
}


@pytest.mark.parametrize(("filename", "expected"), AGENTS.items())
def test_review_agent_is_structurally_read_only(filename: str, expected: ExpectedAgent) -> None:
    agent = tomllib.loads((AGENT_DIRECTORY / filename).read_text(encoding="utf-8"))

    assert agent["name"] == expected.name
    assert agent["sandbox_mode"] == "read-only"
    assert isinstance(agent["description"], str) and agent["description"].strip()
    instructions = agent["developer_instructions"]
    assert isinstance(instructions, str)
    assert "NO_ACTION" in instructions
    assert "MATERIAL_ISSUE" in instructions

    normalized_instructions = " ".join(instructions.lower().split())
    for requirement in expected.requirements:
        assert requirement in normalized_instructions


def test_review_agent_names_are_unique() -> None:
    names = {
        tomllib.loads(path.read_text(encoding="utf-8"))["name"]
        for path in AGENT_DIRECTORY.glob("reefproof-*.toml")
    }
    assert names == {expected.name for expected in AGENTS.values()}


def test_repository_documents_single_reviewer_workflow() -> None:
    guide = (ROOT / "docs" / "player-coach-loop.md").read_text(encoding="utf-8")
    agent_guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    combined = f"{agent_guide}\n{guide}"

    assert "reefproof_reviewer" in combined
    for required in (
        "only writer",
        "Run project grounding",
        "one narrow coherent slice",
        "focused tests",
        "one final deterministic",
        "human for acceptance",
        "NO_ACTION",
        "MATERIAL_ISSUE",
    ):
        assert required in combined


def test_contributor_guidance_does_not_route_agents_to_superseded_coach() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    historical_plan = (ROOT / "docs" / "plans" / "2026-07-25-player-coach-protocol.md").read_text(
        encoding="utf-8"
    )

    assert "docs/player-coach-loop.md" in contributing
    assert "2026-07-25-player-coach-protocol.md" not in contributing
    assert "Status: Superseded" in historical_plan
    assert "Do not use this plan as current agent guidance" in historical_plan


def test_agent_guide_is_a_compact_safety_first_task_contract() -> None:
    guide = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized = " ".join(guide.split())

    assert len(guide.splitlines()) <= 110
    assert guide.index("1. Permanent safety boundary.") < guide.index(
        "2. Current explicit human instruction."
    )
    for required in (
        "Read-only review",
        "Small compatible repair",
        "Material change",
        "attached-TTY `./reefproof`",
        "focused tests plus the exact interface acceptance",
        "Never discard, reset, stash, stage, or commit unexplained existing work",
        "stop before editing that file",
        "repository-root `make help`",
        "repository-owned local-CI skill",
        "Do not copy low-level commands from historical plans",
    ):
        assert required in normalized
    assert "about 2.6 KB" not in normalized
    assert "GIT_CONFIG_GLOBAL" not in normalized
