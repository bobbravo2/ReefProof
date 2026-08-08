from __future__ import annotations

import json
from pathlib import Path

from reefproof.usage import load_records
from reefproof.usage_hooks import import_transcript, load_turns, transcript_turns


def _transcript(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                '{"type":"item.completed","item":{"type":"agent_message","text":"private"}}',
                '{"type":"turn.completed","turn_id":"turn-1","usage":'
                '{"input_tokens":10,"cached_input_tokens":4,"output_tokens":3,'
                '"reasoning_output_tokens":1}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_hook_import_stores_only_sanitized_turn_usage(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    _transcript(transcript)

    turns = transcript_turns(
        transcript,
        session_id="session-1",
        fallback_turn_id=None,
        model="test-model",
    )

    assert turns[0]["tokens"]["input"] == 10
    assert turns[0]["tokens"]["total"] is None
    serialized = json.dumps(turns)
    assert "private" not in serialized
    assert "agent_message" not in serialized


def test_missing_hook_usage_remains_unknown(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"type":"unrecognized"}\n', encoding="utf-8")

    turns = transcript_turns(
        transcript,
        session_id="session-1",
        fallback_turn_id="turn-1",
        model=None,
    )

    assert all(value is None for value in turns[0]["tokens"].values())
    assert turns[0]["usage_source"] == "unknown"


def test_interactive_session_summary_uses_latest_cumulative_counter(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                '{"type":"event_msg","payload":{"type":"token_count","info":'
                '{"total_token_usage":{"input_tokens":10,"cached_input_tokens":4,'
                '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}}}',
                '{"type":"event_msg","payload":{"type":"token_count","info":'
                '{"total_token_usage":{"input_tokens":20,"cached_input_tokens":8,'
                '"output_tokens":5,"reasoning_output_tokens":2,"total_tokens":25}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    turns = transcript_turns(
        transcript,
        session_id="session-1",
        fallback_turn_id="turn-1",
        model="test-model",
    )

    assert len(turns) == 1
    assert turns[0]["turn_id"] == "session-total"
    assert turns[0]["usage_source"] == "codex-session-summary"
    assert turns[0]["tokens"] == {
        "input": 20,
        "cached_input": 8,
        "output": 5,
        "reasoning": 2,
        "total": 25,
    }


def test_interactive_session_summary_is_repaired_as_counter_grows(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    turns_path = tmp_path / "turns.jsonl"
    ledger_path = tmp_path / "sessions.jsonl"
    transcript.write_text(
        '{"type":"event_msg","payload":{"type":"token_count","info":'
        '{"total_token_usage":{"input_tokens":10,"cached_input_tokens":4,'
        '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}}}\n',
        encoding="utf-8",
    )
    import_transcript(
        transcript_path=transcript,
        session_id="session-1",
        turn_id=None,
        model="test-model",
        event_name="Stop",
        turns_path=turns_path,
        ledger_path=ledger_path,
    )
    transcript.write_text(
        '{"type":"event_msg","payload":{"type":"token_count","info":'
        '{"total_token_usage":{"input_tokens":20,"cached_input_tokens":8,'
        '"output_tokens":5,"reasoning_output_tokens":2,"total_tokens":25}}}}\n',
        encoding="utf-8",
    )

    result = import_transcript(
        transcript_path=transcript,
        session_id="session-1",
        turn_id=None,
        model="test-model",
        event_name="SessionEnd",
        turns_path=turns_path,
        ledger_path=ledger_path,
    )

    assert result == {"turns_added": 0, "turns_repaired": 1}
    assert load_records(ledger_path)[0]["tokens"]["total"] == 25


def test_import_repairs_unknown_usage_without_changing_completed_outcome(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    turns_path = tmp_path / "turns.jsonl"
    ledger_path = tmp_path / "sessions.jsonl"
    transcript.write_text(
        '{"type":"event_msg","payload":{"type":"token_count","info":'
        '{"total_token_usage":{"input_tokens":20,"cached_input_tokens":8,'
        '"output_tokens":5,"reasoning_output_tokens":2,"total_tokens":25}}}}\n',
        encoding="utf-8",
    )
    _transcript_record = {
        "schema_version": "0.1",
        "session_id": "session-1",
        "task": "completed task",
        "started_at": "2026-07-25T10:00:00-04:00",
        "ended_at": "2026-07-25T10:10:00-04:00",
        "model": None,
        "reasoning_level": None,
        "git_start": None,
        "git_end": "working-tree",
        "usage_source": "unknown",
        "tokens": dict.fromkeys(("input", "cached_input", "output", "reasoning", "total")),
        "usage_limits": {
            "five_hour_remaining_start_percent": None,
            "five_hour_remaining_end_percent": None,
            "weekly_remaining_start_percent": None,
            "weekly_remaining_end_percent": None,
        },
        "authoritative_cost_usd": None,
        "wall_seconds": 600,
        "files_changed": 2,
        "lines_added": 10,
        "lines_removed": 1,
        "targeted_test_runs": 1,
        "full_check_runs": 1,
        "acceptance_criteria_passed": 2,
        "acceptance_criteria_total": 2,
        "result": "completed",
        "notes": [],
    }
    ledger_path.write_text(json.dumps(_transcript_record) + "\n", encoding="utf-8")

    import_transcript(
        transcript_path=transcript,
        session_id="session-1",
        turn_id=None,
        model="test-model",
        event_name="Stop",
        turns_path=turns_path,
        ledger_path=ledger_path,
    )

    repaired = load_records(ledger_path)[0]
    assert repaired["tokens"]["total"] == 25
    assert repaired["result"] == "completed"
    assert repaired["wall_seconds"] == 600
    assert repaired["acceptance_criteria_passed"] == 2


def test_repair_import_is_idempotent(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    turns_path = tmp_path / "turns.jsonl"
    ledger_path = tmp_path / "sessions.jsonl"
    _transcript(transcript)

    first = import_transcript(
        transcript_path=transcript,
        session_id="session-1",
        turn_id=None,
        model="test-model",
        event_name="SessionEnd",
        turns_path=turns_path,
        ledger_path=ledger_path,
    )
    second = import_transcript(
        transcript_path=transcript,
        session_id="session-1",
        turn_id=None,
        model="test-model",
        event_name="SessionEnd",
        turns_path=turns_path,
        ledger_path=ledger_path,
    )

    assert first == {"turns_added": 1, "turns_repaired": 0}
    assert second == {"turns_added": 0, "turns_repaired": 0}
    assert len(load_turns(turns_path)) == 1
    assert len(load_records(ledger_path)) == 1
    assert load_records(ledger_path)[0]["authoritative_cost_usd"] is None
