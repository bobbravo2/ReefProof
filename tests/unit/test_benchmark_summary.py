from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    path = ROOT / "scripts" / "summarize-codex-benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark_summary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_summary_reports_tokens_tools_timing_and_valid_result(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 60,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    final_message = tmp_path / "final-message.txt"
    final_message.write_text(
        "STATE: INITIAL_TASK\nRESULT: READY\n\nEVIDENCE:\n- Grounding succeeded.\n",
        encoding="utf-8",
    )

    summary = _module().summarize(
        events_path=events,
        final_message_path=final_message,
        codex_version="test",
        wall_seconds=7,
    )

    assert summary["result_valid"] is True
    assert summary["wall_seconds"] == 7
    assert summary["event_count"] == 2
    assert summary["tool_call_count"] == 1
    assert summary["tokens"] == {
        "input": 100,
        "cached_input": 60,
        "output": 20,
        "reasoning": 5,
        "total": None,
    }
    assert summary["telemetry_error"] is None


def test_summary_preserves_unknown_tokens_for_missing_usage(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"turn.started"}\n', encoding="utf-8")
    final_message = tmp_path / "final-message.txt"
    final_message.write_text("unexpected", encoding="utf-8")

    summary = _module().summarize(
        events_path=events,
        final_message_path=final_message,
        codex_version="test",
        wall_seconds=1,
    )

    assert summary["result_valid"] is False
    tokens = summary["tokens"]
    assert isinstance(tokens, dict)
    assert all(value is None for value in tokens.values())
    assert summary["telemetry_error"] == "Codex JSON contains no turn.completed usage event"


def test_summary_handles_missing_final_message(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"type":"turn.completed","usage":{"input_tokens":1,'
        '"cached_input_tokens":0,"output_tokens":1,"reasoning_output_tokens":0}}\n',
        encoding="utf-8",
    )

    summary = _module().summarize(
        events_path=events,
        final_message_path=tmp_path / "missing.txt",
        codex_version="test",
        wall_seconds=1,
    )

    assert summary["result_valid"] is False
