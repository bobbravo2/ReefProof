from __future__ import annotations

import json
import socket
from pathlib import Path

from typer.testing import CliRunner

from reefproof.cli import app

runner = CliRunner()


def test_infra_smoke_initializes_then_verifies_deterministically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_directory = tmp_path / "evidence"
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))

    first = runner.invoke(app, ["infra-smoke", "--format", "json"])
    second = runner.invoke(app, ["infra-smoke", "--format", "json"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    assert first.stdout == second.stdout
    document = json.loads(first.stdout)
    assert document["evidence_provenance"] == "AUTHORED"
    assert document["evidence_source_format"] == "synthetic"
    assert document["idempotent"] is True
    assert document["integrity"] == "ok"
    assert document["transition_count"] == 2
    assert (data_directory / "reefproof.sqlite3").is_file()


def test_infra_smoke_never_opens_a_network_connection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(tmp_path / "evidence"))

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)

    result = runner.invoke(app, ["infra-smoke", "--format", "json"])

    assert result.exit_code == 0, result.stdout


def test_storage_schema_and_verify_support_restore_checks(tmp_path: Path, monkeypatch) -> None:
    data_directory = tmp_path / "evidence"
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))

    uninitialized = runner.invoke(app, ["database", "schema"])
    assert uninitialized.exit_code == 0
    assert json.loads(uninitialized.stdout)["initialized"] is False

    assert runner.invoke(app, ["infra-smoke"]).exit_code == 0
    schema = runner.invoke(app, ["database", "schema"])
    verify = runner.invoke(app, ["database", "verify"])

    assert schema.exit_code == 0, schema.stdout
    assert json.loads(schema.stdout)["schema_version"] == 1
    assert verify.exit_code == 0, verify.stdout
    assert json.loads(verify.stdout)["status"] == "PASS"


def test_storage_verify_reports_corruption(tmp_path: Path, monkeypatch) -> None:
    data_directory = tmp_path / "evidence"
    data_directory.mkdir()
    (data_directory / "reefproof.sqlite3").write_text("not a sqlite database", encoding="utf-8")
    monkeypatch.setenv("REEFPROOF_DATA_DIRECTORY", str(data_directory))

    result = runner.invoke(app, ["database", "verify"])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "FAIL"
