"""Append-only persistence for commissioning proof and dispositions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from reefproof.commissioning import CommissioningVerification, FailureModeDisposition


class CommissioningStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        uri = f"{self.path.resolve().as_uri()}?mode=rw"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def record_verification(self, record: CommissioningVerification) -> None:
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO commissioning_verifications(
                    verification_id, project_id, device_id, kind, outcome,
                    verified_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.verification_id,
                    record.project_id,
                    record.device_id,
                    record.kind.value,
                    record.outcome.value,
                    record.verified_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def list_verifications(self, project_id: str) -> tuple[CommissioningVerification, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_json FROM commissioning_verifications "
                "WHERE project_id = ? ORDER BY verified_at, verification_id",
                (project_id,),
            ).fetchall()
        return tuple(
            CommissioningVerification.model_validate_json(row["document_json"]) for row in rows
        )

    def record_disposition(self, record: FailureModeDisposition) -> None:
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT INTO failure_mode_dispositions(
                    disposition_id, project_id, device_id, failure_mode_id,
                    disposition, decided_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.disposition_id,
                    record.project_id,
                    record.device_id,
                    record.failure_mode_id,
                    record.disposition.value,
                    record.decided_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def list_dispositions(self, project_id: str) -> tuple[FailureModeDisposition, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT document_json FROM failure_mode_dispositions "
                "WHERE project_id = ? ORDER BY decided_at, disposition_id",
                (project_id,),
            ).fetchall()
        return tuple(
            FailureModeDisposition.model_validate_json(row["document_json"]) for row in rows
        )
