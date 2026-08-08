"""Harness-neutral, append-preserving agent usage ledger."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, cast

SCHEMA_VERSION: Final = "0.1"
VALID_USAGE_SOURCES: Final = {
    "codex-json",
    "codex-status",
    "codex-session-summary",
    "harness",
    "manual",
    "unknown",
}
VALID_RESULTS: Final = {"in_progress", "completed", "partial", "blocked", "failed"}
type TokenKey = Literal["input", "cached_input", "output", "reasoning", "total"]
type TokenMap = dict[TokenKey, int | None]
type JsonObject = dict[str, object]

TOKEN_KEYS: Final[tuple[TokenKey, ...]] = (
    "input",
    "cached_input",
    "output",
    "reasoning",
    "total",
)
LIMIT_KEYS: Final = (
    "five_hour_remaining_start_percent",
    "five_hour_remaining_end_percent",
    "weekly_remaining_start_percent",
    "weekly_remaining_end_percent",
)
FORBIDDEN_CONTENT_KEYS: Final = {
    "prompt",
    "prompts",
    "response",
    "responses",
    "conversation",
    "messages",
    "credential",
    "credentials",
}


class LedgerError(ValueError):
    """A ledger record or operation is unsafe or malformed."""


def normalize_json_object(value: object, message: str) -> JsonObject:
    """Narrow one untrusted JSON boundary to an object with string keys."""

    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise LedgerError(message)
    return cast(JsonObject, value)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_ledger_path() -> Path:
    override = os.environ.get("REEFPROOF_USAGE_LEDGER")
    return Path(override) if override else repository_root() / ".agent/usage/sessions.jsonl"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _git_identity(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _contains_forbidden_content(value: object) -> bool:
    if isinstance(value, dict):
        normalized = cast(dict[object, object], value)
        return any(
            str(key).lower() in FORBIDDEN_CONTENT_KEYS or _contains_forbidden_content(item)
            for key, item in normalized.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_content(item) for item in value)
    return False


def _nullable_nonnegative(record: dict[str, Any], key: str) -> None:
    value = record.get(key)
    if value is not None and (
        not isinstance(value, int | float) or isinstance(value, bool) or value < 0
    ):
        raise LedgerError(f"{key} must be null or non-negative")


def validate_record(record: object) -> dict[str, Any]:
    record = cast(
        dict[str, Any],
        normalize_json_object(record, "record must be a JSON object"),
    )
    if _contains_forbidden_content(record):
        raise LedgerError("record contains a forbidden conversational or credential field")

    required = {
        "schema_version",
        "session_id",
        "task",
        "started_at",
        "ended_at",
        "model",
        "reasoning_level",
        "git_start",
        "git_end",
        "usage_source",
        "tokens",
        "usage_limits",
        "authoritative_cost_usd",
        "wall_seconds",
        "files_changed",
        "lines_added",
        "lines_removed",
        "targeted_test_runs",
        "full_check_runs",
        "acceptance_criteria_passed",
        "acceptance_criteria_total",
        "result",
        "notes",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise LedgerError(f"missing required fields: {', '.join(missing)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise LedgerError(f"unsupported schema_version: {record['schema_version']}")
    if not isinstance(record["session_id"], str) or not record["session_id"].strip():
        raise LedgerError("session_id must be a non-empty string")
    if not isinstance(record["task"], str) or not record["task"].strip():
        raise LedgerError("task must be a non-empty string")
    if not isinstance(record["started_at"], str):
        raise LedgerError("started_at must be a string")
    if record["ended_at"] is not None and not isinstance(record["ended_at"], str):
        raise LedgerError("ended_at must be null or a string")
    if record["usage_source"] not in VALID_USAGE_SOURCES:
        raise LedgerError(f"invalid usage_source: {record['usage_source']}")
    if record["result"] not in VALID_RESULTS:
        raise LedgerError(f"invalid result: {record['result']}")
    if not isinstance(record["tokens"], dict) or set(record["tokens"]) != set(TOKEN_KEYS):
        raise LedgerError("tokens must contain exactly the supported token classes")
    for key in TOKEN_KEYS:
        _nullable_nonnegative(record["tokens"], key)
    if not isinstance(record["usage_limits"], dict) or set(record["usage_limits"]) != set(
        LIMIT_KEYS
    ):
        raise LedgerError("usage_limits must contain exactly the supported limit fields")
    for key in LIMIT_KEYS:
        _nullable_nonnegative(record["usage_limits"], key)
        value = record["usage_limits"][key]
        if value is not None and value > 100:
            raise LedgerError(f"{key} must be at most 100")
    for key in (
        "authoritative_cost_usd",
        "wall_seconds",
        "files_changed",
        "lines_added",
        "lines_removed",
        "targeted_test_runs",
        "full_check_runs",
        "acceptance_criteria_passed",
        "acceptance_criteria_total",
    ):
        _nullable_nonnegative(record, key)
    if not isinstance(record["notes"], list) or not all(
        isinstance(note, str) for note in record["notes"]
    ):
        raise LedgerError("notes must be a list of strings")
    if record["result"] == "in_progress" and record["ended_at"] is not None:
        raise LedgerError("in-progress records may not have ended_at")
    if record["result"] != "in_progress" and record["ended_at"] is None:
        raise LedgerError("completed records require ended_at")
    if record["acceptance_criteria_passed"] > record["acceptance_criteria_total"]:
        raise LedgerError("acceptance criteria passed exceeds total")
    return record


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
    ledger = path or default_ledger_path()
    if not ledger.exists():
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise LedgerError(f"blank line at {line_number}")
        try:
            decoded = cast(object, json.loads(line))
            record = validate_record(decoded)
        except (json.JSONDecodeError, LedgerError) as error:
            raise LedgerError(f"line {line_number}: {error}") from error
        if record["session_id"] in seen:
            raise LedgerError(f"line {line_number}: duplicate session_id")
        seen.add(record["session_id"])
        records.append(record)
    return records


def _atomic_write(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".sessions.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, separators=(",", ":"), sort_keys=False))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def new_record(
    *,
    task: str,
    session_id: str | None = None,
    budget_total: int | None = None,
    budget_output: int | None = None,
) -> dict[str, Any]:
    identifier = session_id or f"{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:8]}"
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": identifier,
        "task": task,
        "started_at": _now(),
        "ended_at": None,
        "model": None,
        "reasoning_level": None,
        "git_start": _git_identity(repository_root()),
        "git_end": None,
        "usage_source": "unknown",
        "tokens": dict.fromkeys(TOKEN_KEYS),
        "usage_limits": dict.fromkeys(LIMIT_KEYS),
        "authoritative_cost_usd": None,
        "wall_seconds": None,
        "files_changed": None,
        "lines_added": None,
        "lines_removed": None,
        "targeted_test_runs": 0,
        "full_check_runs": 0,
        "acceptance_criteria_passed": 0,
        "acceptance_criteria_total": 0,
        "result": "in_progress",
        "token_budget": {
            "total_observed": budget_total,
            "output": budget_output,
            "full_check_runs": 3,
        },
        "notes": [],
    }
    return validate_record(record)


def start_session(
    *,
    path: Path,
    task: str,
    session_id: str | None,
    budget_total: int | None,
    budget_output: int | None,
) -> dict[str, Any]:
    records = load_records(path)
    record = new_record(
        task=task,
        session_id=session_id,
        budget_total=budget_total,
        budget_output=budget_output,
    )
    if any(existing["session_id"] == record["session_id"] for existing in records):
        raise LedgerError(f"session already exists: {record['session_id']}")
    _atomic_write(path, [*records, record])
    return record


def parse_codex_json(path: Path, *, codex_version: str) -> TokenMap:
    if not codex_version:
        raise LedgerError("--codex-version is required for Codex JSON input")
    totals: TokenMap = {key: None for key in TOKEN_KEYS}
    found = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            decoded = cast(object, json.loads(line))
            event = normalize_json_object(
                decoded,
                f"Codex JSON line {line_number} is not an object",
            )
        except json.JSONDecodeError as error:
            raise LedgerError(f"Codex JSON line {line_number} is malformed") from error
        if not isinstance(event.get("type"), str):
            raise LedgerError(f"Codex JSON line {line_number} is not a recognized event")
        if event["type"] != "turn.completed":
            continue
        usage_value = event.get("usage")
        if not isinstance(usage_value, dict):
            raise LedgerError("turn.completed event has no valid usage object")
        usage = normalize_json_object(
            usage_value,
            "turn.completed usage is not an object",
        )
        source_keys: dict[TokenKey, str] = {
            "input": "input_tokens",
            "cached_input": "cached_input_tokens",
            "output": "output_tokens",
            "reasoning": "reasoning_output_tokens",
        }
        parsed: dict[TokenKey, int] = {}
        for target, source in source_keys.items():
            value = usage.get(source)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise LedgerError(f"turn.completed usage field {source} is malformed")
            parsed[target] = value
        for key, value in parsed.items():
            previous = totals[key]
            totals[key] = value + (previous if isinstance(previous, int) else 0)
        found = True
    if not found:
        raise LedgerError("Codex JSON contains no turn.completed usage event")
    # The documented event has no total field. Preserve UNKNOWN instead of
    # inventing a total that may omit future or differently-accounted classes.
    totals["total"] = None
    return totals


def _find_in_progress(records: list[dict[str, Any]], session_id: str) -> int:
    for index, record in enumerate(records):
        if record["session_id"] == session_id:
            if record["result"] != "in_progress":
                raise LedgerError("historical completed entries are append-only")
            return index
    raise LedgerError(f"unknown session: {session_id}")


def _resolve_in_progress_session(records: list[dict[str, Any]], session_id: str | None) -> str:
    if session_id is not None:
        return session_id
    active = [record["session_id"] for record in records if record["result"] == "in_progress"]
    if len(active) != 1:
        raise LedgerError("finish without --session-id requires exactly one in-progress session")
    return cast(str, active[0])


def record_codex_usage(
    *,
    path: Path,
    session_id: str,
    codex_json: Path,
    codex_version: str,
) -> dict[str, Any]:
    records = load_records(path)
    index = _find_in_progress(records, session_id)
    updated = {**records[index]}
    updated["tokens"] = parse_codex_json(codex_json, codex_version=codex_version)
    updated["usage_source"] = "codex-json"
    updated["notes"] = [*updated["notes"], f"Codex JSON adapter version: {codex_version}"]
    records[index] = validate_record(updated)
    _atomic_write(path, records)
    return records[index]


def record_manual_usage(
    *,
    path: Path,
    session_id: str,
    tokens: dict[str, int | None],
    usage_source: str,
) -> dict[str, Any]:
    if usage_source not in VALID_USAGE_SOURCES - {"codex-json", "unknown"}:
        raise LedgerError("manual recording requires a declared observable source")
    if all(value is None for value in tokens.values()):
        raise LedgerError("manual recording requires at least one observed token value")
    records = load_records(path)
    index = _find_in_progress(records, session_id)
    updated = {**records[index], "tokens": tokens, "usage_source": usage_source}
    records[index] = validate_record(updated)
    _atomic_write(path, records)
    return records[index]


def _git_change_counts(root: Path) -> tuple[int, int, int]:
    files = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    numstat = subprocess.run(
        ["git", "-C", str(root), "diff", "--numstat", "--no-renames"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    added = 0
    removed = 0
    for line in numstat:
        before, after, *_ = line.split("\t")
        if before.isdigit():
            added += int(before)
        if after.isdigit():
            removed += int(after)
    for status_line in files:
        if not status_line.startswith("?? "):
            continue
        candidate = root / status_line[3:]
        if not candidate.is_file():
            continue
        try:
            added += len(candidate.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            continue
    return len(files), added, removed


def finish_session(
    *,
    path: Path,
    session_id: str | None,
    result: str,
    targeted_test_runs: int,
    full_check_runs: int,
    acceptance_passed: int,
    acceptance_total: int,
    residual_risk: str | None,
    next_task: str | None,
) -> dict[str, Any]:
    if result == "in_progress":
        raise LedgerError("finish result must be terminal")
    records = load_records(path)
    resolved_session_id = _resolve_in_progress_session(records, session_id)
    index = _find_in_progress(records, resolved_session_id)
    current = records[index]
    start = datetime.fromisoformat(current["started_at"])
    end = datetime.now().astimezone()
    files_changed, lines_added, lines_removed = _git_change_counts(repository_root())
    notes = list(current["notes"])
    if residual_risk:
        notes.append(f"Residual risk: {residual_risk}")
    if next_task:
        notes.append(f"Exact next task: {next_task}")
    updated = {
        **current,
        "ended_at": end.isoformat(timespec="seconds"),
        "git_end": _git_identity(repository_root()) or "working-tree",
        "wall_seconds": max(0, int((end - start).total_seconds())),
        "files_changed": files_changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "targeted_test_runs": targeted_test_runs,
        "full_check_runs": full_check_runs,
        "acceptance_criteria_passed": acceptance_passed,
        "acceptance_criteria_total": acceptance_total,
        "result": result,
        "notes": notes,
    }
    records[index] = validate_record(updated)
    _atomic_write(path, records)
    return records[index]


def aggregate(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    tokens: dict[str, int | None] = {}
    for key in TOKEN_KEYS:
        values = [record["tokens"][key] for record in records]
        known = [value for value in values if isinstance(value, int)]
        tokens[key] = sum(known) if known and len(known) == len(values) else None
    costs = [record["authoritative_cost_usd"] for record in records]
    cost = (
        sum(value for value in costs if isinstance(value, int | float))
        if costs
        and all(isinstance(value, int | float) and not isinstance(value, bool) for value in costs)
        else None
    )
    wall_values = [record["wall_seconds"] for record in records]
    wall = (
        sum(value for value in wall_values if isinstance(value, int))
        if wall_values and all(isinstance(value, int) for value in wall_values)
        else None
    )
    input_tokens = tokens["input"]
    output_tokens = tokens["output"]
    acceptance = sum(record["acceptance_criteria_passed"] for record in records)
    total_acceptance = sum(record["acceptance_criteria_total"] for record in records)
    return {
        "sessions": len(records),
        "results": [record["result"] for record in records],
        "wall_seconds": wall,
        "tokens": tokens,
        "authoritative_cost_usd": cost,
        "engineering_outcome": {
            "acceptance_criteria_passed": acceptance,
            "acceptance_criteria_total": total_acceptance,
            "files_changed": sum(
                record["files_changed"]
                for record in records
                if isinstance(record["files_changed"], int)
            )
            if records and all(isinstance(record["files_changed"], int) for record in records)
            else None,
            "targeted_test_runs": sum(record["targeted_test_runs"] for record in records),
            "full_check_runs": sum(record["full_check_runs"] for record in records),
        },
        "efficiency_signals": {
            "output_to_input_ratio": (
                output_tokens / input_tokens
                if isinstance(input_tokens, int)
                and input_tokens > 0
                and isinstance(output_tokens, int)
                else None
            ),
            "tokens_per_completed_acceptance_criterion": (
                tokens["total"] / acceptance
                if isinstance(tokens["total"], int) and acceptance > 0
                else None
            ),
            "rework_count": None,
        },
    }


def _display(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def human_summary(summary: dict[str, Any]) -> str:
    tokens = summary["tokens"]
    outcome = summary["engineering_outcome"]
    results = ", ".join(summary["results"]) if summary["results"] else "UNKNOWN"
    wall = summary["wall_seconds"]
    wall_text = (
        f"{wall // 3600}h {(wall % 3600) // 60}m {wall % 60}s"
        if isinstance(wall, int)
        else "UNKNOWN"
    )
    return "\n".join(
        [
            "Agent usage — ReefProof",
            "",
            f"Sessions:             {summary['sessions']}",
            f"Result:               {results}",
            f"Wall time:            {wall_text}",
            f"Input tokens:         {_display(tokens['input'])}",
            f"Cached input tokens:  {_display(tokens['cached_input'])}",
            f"Output tokens:        {_display(tokens['output'])}",
            f"Reasoning tokens:     {_display(tokens['reasoning'])}",
            f"Total tokens:         {_display(tokens['total'])}",
            f"Authoritative cost:   {_display(summary['authoritative_cost_usd'])}",
            "",
            "Engineering outcome:",
            "  Acceptance criteria: "
            f"{outcome['acceptance_criteria_passed']}/{outcome['acceptance_criteria_total']}",
            f"  Files changed:       {_display(outcome['files_changed'])}",
            f"  Targeted test runs:  {outcome['targeted_test_runs']}",
            f"  Full check runs:     {outcome['full_check_runs']}",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the ReefProof agent usage ledger")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--ledger", type=Path, default=default_ledger_path())
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--task", required=True)
    start.add_argument("--session-id")
    start.add_argument("--budget-total", type=int)
    start.add_argument("--budget-output", type=int)

    finish = subparsers.add_parser("finish")
    finish.add_argument("--session-id")
    finish.add_argument(
        "--result", choices=sorted(VALID_RESULTS - {"in_progress"}), default="completed"
    )
    finish.add_argument("--targeted-test-runs", type=int, default=0)
    finish.add_argument("--full-check-runs", type=int, default=0)
    finish.add_argument("--acceptance-passed", type=int, default=0)
    finish.add_argument("--acceptance-total", type=int, default=0)
    finish.add_argument("--residual-risk")
    finish.add_argument("--next-task")

    record = subparsers.add_parser("record")
    record.add_argument("--session-id", required=True)
    record.add_argument("--codex-json", type=Path)
    record.add_argument("--codex-version")
    record.add_argument(
        "--source",
        choices=sorted(VALID_USAGE_SOURCES - {"codex-json", "unknown"}),
        default="manual",
    )
    record.add_argument("--input", type=int)
    record.add_argument("--cached-input", type=int)
    record.add_argument("--output", type=int)
    record.add_argument("--reasoning", type=int)
    record.add_argument("--total", type=int)

    importer = subparsers.add_parser("import")
    importer.add_argument("--transcript", type=Path, required=True)
    importer.add_argument("--session-id", required=True)
    importer.add_argument("--turn-id")
    importer.add_argument("--model")
    importer.add_argument("--event", choices=("Stop", "SessionEnd"), default="SessionEnd")

    subparsers.add_parser("summary")
    subparsers.add_parser("validate")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    if arguments is None:
        normalized_arguments = list(sys.argv[1:])
        if "--json" in normalized_arguments:
            normalized_arguments.remove("--json")
            normalized_arguments.insert(0, "--json")
        arguments = normalized_arguments
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        if args.command == "start":
            result = start_session(
                path=args.ledger,
                task=args.task,
                session_id=args.session_id,
                budget_total=args.budget_total,
                budget_output=args.budget_output,
            )
        elif args.command == "finish":
            result = finish_session(
                path=args.ledger,
                session_id=args.session_id,
                result=args.result,
                targeted_test_runs=args.targeted_test_runs,
                full_check_runs=args.full_check_runs,
                acceptance_passed=args.acceptance_passed,
                acceptance_total=args.acceptance_total,
                residual_risk=args.residual_risk,
                next_task=args.next_task,
            )
        elif args.command == "record":
            if args.codex_json is not None:
                if args.codex_version is None:
                    raise LedgerError("--codex-version is required with --codex-json")
                result = record_codex_usage(
                    path=args.ledger,
                    session_id=args.session_id,
                    codex_json=args.codex_json,
                    codex_version=args.codex_version,
                )
            else:
                result = record_manual_usage(
                    path=args.ledger,
                    session_id=args.session_id,
                    usage_source=args.source,
                    tokens={
                        "input": args.input,
                        "cached_input": args.cached_input,
                        "output": args.output,
                        "reasoning": args.reasoning,
                        "total": args.total,
                    },
                )
        elif args.command == "import":
            from reefproof.usage_hooks import import_transcript

            result = import_transcript(
                transcript_path=args.transcript,
                session_id=args.session_id,
                turn_id=args.turn_id,
                model=args.model,
                event_name=args.event,
            )
        elif args.command == "summary":
            result = aggregate(load_records(args.ledger))
            if not args.json:
                print(human_summary(result))
                return 0
        else:
            records = load_records(args.ledger)
            from reefproof.usage_hooks import load_turns

            turns = load_turns()
            result = {"valid": True, "records": len(records), "turns": len(turns)}
            if not args.json:
                print(f"PASS: usage ledger valid ({len(records)} session(s), {len(turns)} turn(s))")
                return 0
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"PASS: {args.command} {result.get('session_id', '')}".rstrip())
        return 0
    except (LedgerError, OSError) as error:
        if args.json:
            print(json.dumps({"error": str(error)}))
        else:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
