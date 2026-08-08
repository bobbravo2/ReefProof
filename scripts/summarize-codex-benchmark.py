#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from reefproof.usage import LedgerError, parse_codex_json


def _events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _tool_call_count(events: list[dict[str, Any]]) -> int:
    tool_types = {"command_execution", "mcp_tool_call", "web_search"}
    count = 0
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") in tool_types:
            count += 1
    return count


def _result_valid(final_message: str) -> bool:
    lines = final_message.strip().splitlines()
    if len(lines) < 5 or lines[0] != "STATE: INITIAL_TASK":
        return False
    if lines[1] not in {"RESULT: READY", "RESULT: BLOCKED"}:
        return False
    if lines[2] != "" or lines[3] != "EVIDENCE:":
        return False
    evidence = lines[4:]
    return 1 <= len(evidence) <= 5 and all(line.startswith("- ") for line in evidence)


def summarize(
    *, events_path: Path, final_message_path: Path, codex_version: str, wall_seconds: int
) -> dict[str, object]:
    events = _events(events_path)
    try:
        tokens = parse_codex_json(events_path, codex_version=codex_version)
        telemetry_error: str | None = None
    except LedgerError as error:
        tokens = {key: None for key in ("input", "cached_input", "output", "reasoning", "total")}
        telemetry_error = str(error)
    final_message = (
        final_message_path.read_text(encoding="utf-8") if final_message_path.exists() else ""
    )
    return {
        "schema_version": 1,
        "result_valid": _result_valid(final_message),
        "wall_seconds": wall_seconds,
        "event_count": len(events),
        "tool_call_count": _tool_call_count(events),
        "tokens": tokens,
        "telemetry_error": telemetry_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--final-message", type=Path, required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--wall-seconds", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(
        events_path=args.events,
        final_message_path=args.final_message,
        codex_version=args.codex_version,
        wall_seconds=args.wall_seconds,
    )
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
