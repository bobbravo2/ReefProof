#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

BOUNDED_FILES = (
    ".agent/project-context.json",
    ".agent/next-task.md",
    "AGENTS.md",
    "pyproject.toml",
    "src/reefproof/__init__.py",
)
FORBIDDEN_MANIFEST_KEYS = {
    "version",
    "display_identity",
    "safety_boundary",
    "next_task",
    "git_state",
    "sources",
}
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SAFETY_BOUNDARY = (
    "ReefProof may observe, model, challenge, and alert on a living system. "
    "It may not silently take control of one."
)
AGENT_STEERING_MARKERS = (
    "**Read-only review:**",
    "**Small compatible repair:**",
    "**Material change:**",
    "CLI or REPL: exercise the affected path through attached-TTY `./reefproof`.",
    "API or browser: start the service and inspect the affected endpoint or browser",
    "Shell launcher: run `bash -n` on the shell file.",
    "Internal Python behavior: run focused automated tests.",
)
AGENT_STEERING = {
    "routes": "review=inspect/report;repair=focused+exact-interface;material=plan+repo-gate+human",
    "validation": (
        "cli/repl=attached-TTY;api/browser=affected-flow;shell=bash-n;python=focused-tests"
    ),
    "dirty_tree": "preserve-WIP;inspect-task-diff;stop-on-unclear-overlap",
}


def read_text(repo: Path, relative_path: str) -> str:
    return (repo / relative_path).read_text(encoding="utf-8")


def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    # Sandbox runs may block access to ~/.gitconfig; use a neutral global config.
    env.setdefault("GIT_CONFIG_GLOBAL", "/dev/null")
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        command = " ".join(["git", *args])
        stderr = completed.stderr.strip() or "(no stderr)"
        raise RuntimeError(f"{command} failed with exit {completed.returncode}: {stderr}")
    return completed.stdout.strip()


def _read_once(repo: Path) -> dict[str, str]:
    return {relative_path: read_text(repo, relative_path) for relative_path in BOUNDED_FILES}


def _validate_non_empty_trimmed(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _validate_manifest(manifest: dict[str, object], repo: Path) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    product = manifest.get("product")
    if not isinstance(product, dict):
        raise ValueError("manifest product must be an object")
    extra = sorted(set(product) & FORBIDDEN_MANIFEST_KEYS)
    if extra:
        raise ValueError(f"manifest product must not define: {', '.join(extra)}")
    _validate_non_empty_trimmed(product.get("name"), "manifest product.name")
    if any(key in manifest for key in ("safety_boundary", "next_task", "git_state", "sources")):
        raise ValueError("manifest contains derived top-level fields")
    architecture = manifest.get("architecture")
    if not isinstance(architecture, dict):
        raise ValueError("manifest architecture must be an object")
    for key in ("main_cli_entrypoint", "runtime_composition_entrypoint", "persistence_entrypoint"):
        path = architecture.get(key)
        if not isinstance(path, str) or not path:
            raise ValueError(f"manifest architecture.{key} must be a non-empty string")
        declared = Path(path)
        if declared.is_absolute():
            raise ValueError(f"manifest architecture.{key} must be relative")
        resolved = (repo / declared).resolve()
        if not resolved.is_relative_to(repo.resolve()):
            raise ValueError(f"manifest architecture.{key} must stay inside the repository")
        if not resolved.exists() or not resolved.is_file():
            raise ValueError(f"manifest architecture.{key} must resolve to an existing file")
    for key in ("implemented", "deferred", "absent", "unknowns"):
        value = manifest.get(key)
        if not isinstance(value, list) or not value:
            raise ValueError(f"manifest {key} must be a non-empty list")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"manifest {key} must contain non-empty strings")


def _load_version(files: dict[str, str]) -> str:
    data = tomllib.loads(files["pyproject.toml"])
    version = data["project"]["version"]
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("pyproject.toml version must use major.minor.patch")
    module = files["src/reefproof/__init__.py"]
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', module, re.M)
    if not match:
        raise ValueError("src/reefproof/__init__.py must define __version__")
    if match.group(1) != version:
        raise ValueError("pyproject.toml version must match src/reefproof/__init__.py")
    return version


def _load_next_task(files: dict[str, str]) -> str:
    return _validate_non_empty_trimmed(files[".agent/next-task.md"], ".agent/next-task.md")


def _load_safety_boundary(files: dict[str, str]) -> str:
    if SAFETY_BOUNDARY not in files["AGENTS.md"]:
        raise ValueError("AGENTS.md does not contain the exact permanent safety boundary")
    return SAFETY_BOUNDARY


def _load_agent_steering(files: dict[str, str]) -> dict[str, str]:
    agents = files["AGENTS.md"]
    missing = [marker for marker in AGENT_STEERING_MARKERS if marker not in agents]
    if missing:
        raise ValueError(f"AGENTS.md does not contain grounding steering marker: {missing[0]}")
    return AGENT_STEERING


def build_output(repo: Path, *, include_steering: bool = False) -> dict[str, object]:
    repo = repo.resolve()
    files = _read_once(repo)
    manifest = json.loads(files[".agent/project-context.json"])
    _validate_manifest(manifest, repo)
    version = _load_version(files)
    name = _validate_non_empty_trimmed(manifest["product"]["name"], "manifest product.name")  # type: ignore[index]
    display_identity = f"{name} {version}"
    next_task = _load_next_task(files)
    output: dict[str, object] = {
        "schema_version": 1,
        "product": {
            "name": name,
            "version": version,
            "display_identity": display_identity,
            "sources": {
                "name": ".agent/project-context.json",
                "version": "pyproject.toml",
            },
        },
        "safety_boundary": {
            "value": _load_safety_boundary(files),
            "source": "AGENTS.md",
        },
        "current_gate": {
            "value": _validate_non_empty_trimmed(manifest["current_gate"], "manifest current_gate"),  # type: ignore[index]
            "source": ".agent/project-context.json",
        },
        "architecture": {
            "value": manifest["architecture"],
            "source": ".agent/project-context.json",
        },
        "implemented": {
            "value": manifest["implemented"],
            "source": ".agent/project-context.json",
        },
        "deferred": {
            "value": manifest["deferred"],
            "source": ".agent/project-context.json",
        },
        "absent": {
            "value": manifest["absent"],
            "source": ".agent/project-context.json",
        },
        "unknowns": {
            "value": manifest["unknowns"],
            "source": ".agent/project-context.json",
        },
        "next_task": {
            "value": next_task,
            "source": ".agent/next-task.md",
        },
        "git_state": {
            "branch": git(repo, "branch", "--show-current"),
            "commit": git(repo, "rev-parse", "HEAD"),
            "working_tree": "dirty" if git(repo, "status", "--short") else "clean",
        },
    }
    if include_steering:
        output["agent_steering"] = _load_agent_steering(files)
    return output


def _compact_whitespace(value: str) -> str:
    return " ".join(value.replace("`", "").split())


def _compact_next_task(value: str) -> list[tuple[str, str]]:
    sections: dict[str, list[str]] = {}
    current = "task"
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or line == "# Next Task":
            continue
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line.removeprefix("- "))

    labels = (
        ("N", "outcome"),
        ("C", "completion criteria"),
        ("B", "boundary"),
    )
    compact = [
        (label, " | ".join(_compact_whitespace(line) for line in sections.get(section, [])))
        for label, section in labels
        if sections.get(section)
    ]
    if compact:
        return compact
    return [("N", _compact_whitespace(value))]


def _print_text(output: dict[str, object]) -> None:
    print(output["product"]["display_identity"])  # type: ignore[index]
    print("PRODUCT")
    print(f"name: {output['product']['name']}")  # type: ignore[index]
    print(f"version: {output['product']['version']}")  # type: ignore[index]
    print("SAFETY BOUNDARY")
    print(output["safety_boundary"]["value"])  # type: ignore[index]
    print("CURRENT GATE")
    print(output["current_gate"]["value"])  # type: ignore[index]
    print("ARCHITECTURE")
    for key, value in output["architecture"]["value"].items():  # type: ignore[index]
        print(f"{key}: {value}")
    print("IMPLEMENTED")
    for item in output["implemented"]["value"]:  # type: ignore[index]
        print(f"- {item}")
    print("DEFERRED")
    for item in output["deferred"]["value"]:  # type: ignore[index]
        print(f"- {item}")
    print("ABSENT")
    for item in output["absent"]["value"]:  # type: ignore[index]
        print(f"- {item}")
    print("UNKNOWNS")
    for item in output["unknowns"]["value"]:  # type: ignore[index]
        print(f"- {item}")
    print("NEXT TASK")
    print(output["next_task"]["value"])  # type: ignore[index]
    print("GIT STATE")
    print(f"branch: {output['git_state']['branch']}")  # type: ignore[index]
    print(f"commit: {output['git_state']['commit']}")  # type: ignore[index]
    print(f"working_tree: {output['git_state']['working_tree']}")  # type: ignore[index]
    print("SOURCES")
    for path in BOUNDED_FILES:
        print(f"- {path}")


def _print_llm(output: dict[str, object], *, include_detail: bool = False) -> None:
    product = output["product"]  # type: ignore[assignment]
    architecture = output["architecture"]["value"]  # type: ignore[index]
    steering = output["agent_steering"]  # type: ignore[assignment]
    git_state = output["git_state"]  # type: ignore[assignment]
    print(f"P {product['display_identity']}")  # type: ignore[index]
    print(f"S {output['safety_boundary']['value']}")  # type: ignore[index]
    print(f"R {steering['routes']}")  # type: ignore[index]
    print(f"V {steering['validation']}")  # type: ignore[index]
    print(f"W {steering['dirty_tree']}")  # type: ignore[index]
    print(f"G {output['current_gate']['value']}")  # type: ignore[index]
    if include_detail:
        architecture_order = (
            "main_cli_entrypoint",
            "runtime_composition_entrypoint",
            "persistence_entrypoint",
        )
        print(
            "A " + ";".join(f"{key}={architecture[key]}" for key in architecture_order)  # type: ignore[index]
        )
        for label, key in (
            ("I", "implemented"),
            ("D", "deferred"),
            ("X", "absent"),
            ("U", "unknowns"),
        ):
            print(f"{label} " + " | ".join(output[key]["value"]))  # type: ignore[index]
    for label, value in _compact_next_task(output["next_task"]["value"]):  # type: ignore[index]
        print(f"{label} {value}")
    print(
        f"T {git_state['branch']}@{git_state['commit']} {git_state['working_tree']}"  # type: ignore[index]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--format", choices=("text", "json", "llm"), default="text")
    parser.add_argument(
        "--detail",
        action="store_true",
        help="include architecture and capability inventories in llm output",
    )
    args = parser.parse_args()
    if args.detail and args.format != "llm":
        parser.error("--detail requires --format llm")
    repo = Path(args.repo)
    try:
        output = build_output(repo, include_steering=args.format == "llm")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    elif args.format == "llm":
        _print_llm(output, include_detail=args.detail)
    else:
        _print_text(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
