from __future__ import annotations

import json

import pytest

from reefproof.logging import configure_logging, usage_event


def test_human_readable_logging_has_stable_event_and_build_identity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(build_identity="test-build")
    usage_event("usage.ledger.validated", records=1)

    captured = capsys.readouterr()
    assert "usage.ledger.validated" in captured.err
    assert "test-build" in captured.err
    assert "records=1" in captured.err


def test_json_logging_contains_no_conversation_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(json_logs=True, build_identity="test-build")
    usage_event("usage.session.finished", result="completed")

    payload = json.loads(capsys.readouterr().err)
    assert payload["event_name"] == "usage.session.finished"
    assert payload["build_identity"] == "test-build"
    assert "prompt" not in payload
    assert "response" not in payload
