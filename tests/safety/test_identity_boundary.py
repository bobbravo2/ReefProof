"""Structural checks for the configured identity boundary."""

import subprocess
from pathlib import Path


def test_executable_product_has_no_person_specific_identity() -> None:
    source_root = Path("src/reefproof")
    forbidden = ("bo" + "b's", "bo" + "bs-reliable")
    hits: list[str] = []

    for path in source_root.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".ts", ".js", ".html"}:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for value in forbidden:
            if value in text:
                hits.append(f"{path}: {value}")

    assert hits == []


def test_tracked_release_sources_have_no_person_or_owner_specific_identity() -> None:
    forbidden = ("bo" + "b's reliable reef", "robert" + "gregor", "robert " + "gregor")
    command = ["git", "grep", "-I", "-i", "-n"]
    for value in forbidden:
        command.extend(("-e", value))
    result = subprocess.run(
        [*command, "--", "."],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout


def test_project_api_does_not_accept_caller_asserted_identity_headers() -> None:
    api_source = Path("src/reefproof/api/projects.py").read_text(encoding="utf-8")

    assert "X-ReefProof-Session-ID" not in api_source
    assert "Header(" not in api_source
