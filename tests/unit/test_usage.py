from __future__ import annotations

import json
from pathlib import Path

import pytest

from reefproof.usage import (
    LedgerError,
    aggregate,
    finish_session,
    load_records,
    new_record,
    parse_codex_json,
    record_codex_usage,
    start_session,
    validate_record,
)


def test_missing_token_values_remain_unknown() -> None:
    record = new_record(task="test", session_id="session")
    summary = aggregate([record])

    assert all(value is None for value in record["tokens"].values())
    assert summary["tokens"]["total"] is None


def test_record_validation_rejects_conversation_content() -> None:
    record = new_record(task="test", session_id="session")
    record["prompt"] = "do not store me"

    with pytest.raises(LedgerError, match="forbidden"):
        validate_record(record)


def test_malformed_record_is_rejected(tmp_path: Path) -> None:
    ledger = tmp_path / "sessions.jsonl"
    ledger.write_text('{"schema_version":"0.1"}\n', encoding="utf-8")

    with pytest.raises(LedgerError, match="missing required fields"):
        load_records(ledger)


def test_completed_entries_are_append_only(tmp_path: Path) -> None:
    ledger = tmp_path / "sessions.jsonl"
    start_session(path=ledger, task="test", session_id="one", budget_total=None, budget_output=None)
    finish_session(
        path=ledger,
        session_id="one",
        result="completed",
        targeted_test_runs=1,
        full_check_runs=1,
        acceptance_passed=1,
        acceptance_total=1,
        residual_risk=None,
        next_task="next",
    )
    before = ledger.read_bytes()
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 2,
                    "output_tokens": 3,
                    "reasoning_output_tokens": 1,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LedgerError, match="append-only"):
        record_codex_usage(
            path=ledger,
            session_id="one",
            codex_json=events,
            codex_version="0.145.0",
        )
    assert ledger.read_bytes() == before


def test_finish_infers_the_only_in_progress_session(tmp_path: Path) -> None:
    ledger = tmp_path / "sessions.jsonl"
    start_session(
        path=ledger,
        task="test",
        session_id="only",
        budget_total=None,
        budget_output=None,
    )

    finished = finish_session(
        path=ledger,
        session_id=None,
        result="completed",
        targeted_test_runs=1,
        full_check_runs=1,
        acceptance_passed=1,
        acceptance_total=1,
        residual_risk=None,
        next_task="next",
    )

    assert finished["session_id"] == "only"
    assert finished["result"] == "completed"


def test_summary_aggregation() -> None:
    first = new_record(task="one", session_id="one")
    second = new_record(task="two", session_id="two")
    first["tokens"] = {
        "input": 10,
        "cached_input": 4,
        "output": 2,
        "reasoning": 1,
        "total": 12,
    }
    second["tokens"] = {
        "input": 20,
        "cached_input": 8,
        "output": 5,
        "reasoning": 2,
        "total": 25,
    }

    summary = aggregate([first, second])

    assert summary["tokens"]["input"] == 30
    assert summary["tokens"]["total"] == 37
    assert summary["authoritative_cost_usd"] is None


def test_malformed_codex_usage_fails_safely(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"turn.completed","usage":{"input_tokens":"many"}}\n', encoding="utf-8"
    )

    with pytest.raises(LedgerError, match="malformed"):
        parse_codex_json(events, codex_version="0.145.0")


def test_codex_usage_adapter_aggregates_documented_events(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                '{"type":"turn.started"}',
                '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,'
                '"output_tokens":3,"reasoning_output_tokens":1}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert parse_codex_json(events, codex_version="0.145.0") == {
        "input": 10,
        "cached_input": 4,
        "output": 3,
        "reasoning": 1,
        "total": None,
    }


def test_dollar_cost_is_never_estimated() -> None:
    record = new_record(task="test", session_id="session")
    record["tokens"]["total"] = 100_000

    assert aggregate([record])["authoritative_cost_usd"] is None
