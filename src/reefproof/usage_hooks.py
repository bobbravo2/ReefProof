"""Sanitized Codex hook transcript adapter.

The transcript format is explicitly unstable. This adapter recognizes only the
documented ``turn.completed.usage`` event shape and represents everything else
as unknown. It never persists transcript content.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Final, cast

from reefproof.usage import (
    TOKEN_KEYS,
    JsonObject,
    LedgerError,
    TokenKey,
    TokenMap,
    aggregate,
    default_ledger_path,
    load_records,
    normalize_json_object,
    validate_record,
)

TURN_SCHEMA_VERSION: Final = "0.1"


def default_turns_path() -> Path:
    override = os.environ.get("REEFPROOF_USAGE_TURNS")
    return Path(override) if override else default_ledger_path().with_name("turns.jsonl")


def _atomic_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _parse_usage(value: object) -> TokenMap:
    unknown: TokenMap = {key: None for key in TOKEN_KEYS}
    if not isinstance(value, dict):
        return unknown
    usage = normalize_json_object(value, "usage is not an object")
    mapping: dict[TokenKey, str] = {
        "input": "input_tokens",
        "cached_input": "cached_input_tokens",
        "output": "output_tokens",
        "reasoning": "reasoning_output_tokens",
    }
    parsed: TokenMap = {key: None for key in TOKEN_KEYS}
    for target, source in mapping.items():
        metric = usage.get(source)
        parsed[target] = (
            metric
            if isinstance(metric, int) and not isinstance(metric, bool) and metric >= 0
            else None
        )
    parsed["total"] = None
    return parsed


def _parse_session_usage(value: object) -> TokenMap:
    """Parse Codex's cumulative interactive-session token counter."""

    parsed = _parse_usage(value)
    if not isinstance(value, dict):
        return parsed
    total = value.get("total_tokens")
    parsed["total"] = (
        total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None
    )
    return parsed


def transcript_turns(
    transcript_path: Path,
    *,
    session_id: str,
    fallback_turn_id: str | None,
    model: str | None,
) -> list[dict[str, Any]]:
    """Extract only documented usage fields; never retain transcript content."""

    if not transcript_path.is_file():
        raise LedgerError(f"transcript is not a readable file: {transcript_path}")
    extracted: list[dict[str, Any]] = []
    session_summary: dict[str, Any] | None = None
    for line_number, line in enumerate(
        transcript_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            decoded = cast(object, json.loads(line))
            event = normalize_json_object(decoded, "transcript event is not an object")
        except json.JSONDecodeError:
            continue
        except LedgerError:
            continue
        payload = event.get("payload")
        if (
            event.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "token_count"
        ):
            info = payload.get("info")
            if isinstance(info, dict):
                tokens = _parse_session_usage(info.get("total_token_usage"))
                if any(value is not None for value in tokens.values()):
                    session_summary = {
                        "schema_version": TURN_SCHEMA_VERSION,
                        "session_id": session_id,
                        "turn_id": "session-total",
                        "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "usage_source": "codex-session-summary",
                        "model": model,
                        "tokens": tokens,
                    }
            continue
        if event.get("type") != "turn.completed":
            continue
        turn_id = event.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            turn_id = fallback_turn_id or f"import-{line_number}"
        extracted.append(
            {
                "schema_version": TURN_SCHEMA_VERSION,
                "session_id": session_id,
                "turn_id": turn_id,
                "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "usage_source": "codex-json",
                "model": model,
                "tokens": _parse_usage(event.get("usage")),
            }
        )
    if session_summary is not None:
        return [session_summary]
    if not extracted and fallback_turn_id:
        extracted.append(
            {
                "schema_version": TURN_SCHEMA_VERSION,
                "session_id": session_id,
                "turn_id": fallback_turn_id,
                "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "usage_source": "unknown",
                "model": model,
                "tokens": dict.fromkeys(TOKEN_KEYS),
            }
        )
    return extracted


def validate_turn(record: object) -> dict[str, Any]:
    record = cast(
        dict[str, Any],
        normalize_json_object(record, "turn summary must be an object"),
    )
    required = {
        "schema_version",
        "session_id",
        "turn_id",
        "observed_at",
        "usage_source",
        "model",
        "tokens",
    }
    if set(record) != required:
        raise LedgerError("turn summary fields are malformed")
    if record["schema_version"] != TURN_SCHEMA_VERSION:
        raise LedgerError("unsupported turn summary schema")
    for key in ("session_id", "turn_id", "observed_at"):
        if not isinstance(record[key], str) or not record[key]:
            raise LedgerError(f"turn {key} must be a non-empty string")
    if record["usage_source"] not in {
        "codex-json",
        "codex-session-summary",
        "unknown",
    }:
        raise LedgerError("unsupported turn usage source")
    if not isinstance(record["tokens"], dict) or set(record["tokens"]) != set(TOKEN_KEYS):
        raise LedgerError("turn token classes are malformed")
    for value in record["tokens"].values():
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise LedgerError("turn token value is malformed")
    return record


def load_turns(path: Path | None = None) -> list[dict[str, Any]]:
    turns_path = path or default_turns_path()
    if not turns_path.exists():
        return []
    turns: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        turns_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            decoded = cast(object, json.loads(line))
            turns.append(validate_turn(decoded))
        except (json.JSONDecodeError, LedgerError) as error:
            raise LedgerError(f"turns line {line_number}: {error}") from error
    return turns


def import_transcript(
    *,
    transcript_path: Path,
    session_id: str,
    turn_id: str | None,
    model: str | None,
    event_name: str,
    turns_path: Path | None = None,
    ledger_path: Path | None = None,
) -> dict[str, int]:
    """Idempotently import a hook transcript and optionally close its session."""

    destination = turns_path or default_turns_path()
    existing = load_turns(destination)
    imported = transcript_turns(
        transcript_path,
        session_id=session_id,
        fallback_turn_id=turn_id,
        model=model,
    )
    indexed = {(record["session_id"], record["turn_id"]): record for record in existing}
    added = 0
    repaired = 0
    for record in imported:
        validate_turn(record)
        key = (record["session_id"], record["turn_id"])
        previous = indexed.get(key)
        if previous is None:
            indexed[key] = record
            added += 1
        elif previous["tokens"] != record["tokens"] and (
            all(value is None for value in previous["tokens"].values())
            or record["usage_source"] == "codex-session-summary"
        ):
            indexed[key] = record
            repaired += 1
    ordered = sorted(indexed.values(), key=lambda item: (item["session_id"], item["turn_id"]))
    _atomic_jsonl(destination, ordered)

    summaries = [record for record in imported if record["usage_source"] == "codex-session-summary"]
    if summaries:
        _repair_ledger_usage(
            session_id=session_id,
            summary=summaries[-1],
            ledger_path=ledger_path or default_ledger_path(),
        )
    if event_name == "SessionEnd":
        _finish_hook_session(
            session_id=session_id,
            model=model,
            turns=[record for record in ordered if record["session_id"] == session_id],
            ledger_path=ledger_path or default_ledger_path(),
        )
    return {"turns_added": added, "turns_repaired": repaired}


def _repair_ledger_usage(
    *,
    session_id: str,
    summary: dict[str, Any],
    ledger_path: Path,
) -> None:
    """Fill previously unknown usage without changing recorded outcomes."""

    records = load_records(ledger_path)
    for index, current in enumerate(records):
        if current["session_id"] != session_id:
            continue
        if not all(value is None for value in current["tokens"].values()):
            return
        updated = {
            **current,
            "tokens": summary["tokens"],
            "usage_source": "codex-session-summary",
            "model": current["model"] or summary["model"],
            "notes": [
                *current["notes"],
                "Token counters repaired from the sanitized Codex session summary.",
            ],
        }
        records[index] = validate_record(updated)
        _atomic_jsonl(ledger_path, records)
        return


def _finish_hook_session(
    *,
    session_id: str,
    model: str | None,
    turns: list[dict[str, Any]],
    ledger_path: Path,
) -> None:
    records = load_records(ledger_path)
    if any(
        record["session_id"] == session_id and record["result"] != "in_progress"
        for record in records
    ):
        return
    session_summaries = [turn for turn in turns if turn["usage_source"] == "codex-session-summary"]
    effective_turns = session_summaries or turns
    turn_aggregate = aggregate(
        [
            {
                "tokens": turn["tokens"],
                "authoritative_cost_usd": None,
                "wall_seconds": None,
                "acceptance_criteria_passed": 0,
                "acceptance_criteria_total": 0,
                "files_changed": None,
                "targeted_test_runs": 0,
                "full_check_runs": 0,
                "result": "completed",
            }
            for turn in effective_turns
        ]
    )
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    record = {
        "schema_version": "0.1",
        "session_id": session_id,
        "task": "Codex hook transcript usage",
        "started_at": now,
        "ended_at": now,
        "model": model,
        "reasoning_level": None,
        "git_start": None,
        "git_end": "UNKNOWN",
        "usage_source": (
            effective_turns[0]["usage_source"]
            if effective_turns and len({turn["usage_source"] for turn in effective_turns}) == 1
            else "unknown"
        ),
        "tokens": turn_aggregate["tokens"] if turns else dict.fromkeys(TOKEN_KEYS),
        "usage_limits": {
            "five_hour_remaining_start_percent": None,
            "five_hour_remaining_end_percent": None,
            "weekly_remaining_start_percent": None,
            "weekly_remaining_end_percent": None,
        },
        "authoritative_cost_usd": None,
        "wall_seconds": None,
        "files_changed": None,
        "lines_added": None,
        "lines_removed": None,
        "targeted_test_runs": 0,
        "full_check_runs": 0,
        "acceptance_criteria_passed": 0,
        "acceptance_criteria_total": 0,
        "result": "completed",
        "notes": [
            "Sanitized automatically from the transcript path supplied by a Codex hook.",
            "Transcript content was not stored.",
        ],
    }
    validate_record(record)
    replaced = False
    for index, current in enumerate(records):
        if current["session_id"] == session_id:
            records[index] = record
            replaced = True
            break
    if not replaced:
        records.append(record)
    _atomic_jsonl(ledger_path, records)


def process_hook_payload(payload: object) -> dict[str, int]:
    hook_payload: JsonObject = normalize_json_object(
        payload,
        "hook payload must be an object",
    )
    event_name = hook_payload.get("hook_event_name")
    if not isinstance(event_name, str) or event_name not in {"Stop", "SessionEnd"}:
        raise LedgerError("unsupported hook event")
    session_id = hook_payload.get("session_id")
    transcript_path = hook_payload.get("transcript_path")
    if not isinstance(session_id, str) or not session_id:
        raise LedgerError("hook payload has no session_id")
    if not isinstance(transcript_path, str) or not transcript_path:
        raise LedgerError("hook payload has no transcript_path")
    turn_id = hook_payload.get("turn_id")
    model = hook_payload.get("model")
    return import_transcript(
        transcript_path=Path(transcript_path),
        session_id=session_id,
        turn_id=turn_id if isinstance(turn_id, str) else None,
        model=model if isinstance(model, str) else None,
        event_name=event_name,
    )


def hook_main() -> int:
    try:
        payload = cast(object, json.load(sys.stdin))
        process_hook_payload(payload)
    except (json.JSONDecodeError, LedgerError, OSError):
        # Hooks are observational and must not block Codex. Unknown remains unknown.
        return 0
    return 0
