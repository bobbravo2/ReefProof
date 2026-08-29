"""Append-only persistence for authored source and import evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from reefproof.authored_sources.models import (
    AuthoredImportBatch,
    AuthoredSourceConfiguration,
    AuthoredSourceFetchAttempt,
    AuthoredSourceSnapshot,
)
from reefproof.authored_sources.review import ExternalIdentityBinding


class AuthoredSourceStore:
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

    def record_configuration(self, configuration: AuthoredSourceConfiguration) -> bool:
        with self._connection() as connection, connection:
            existing = connection.execute(
                "SELECT document_json FROM authored_source_configurations "
                "WHERE source_configuration_id = ?",
                (configuration.source_configuration_id,),
            ).fetchone()
            if existing is not None:
                if (
                    AuthoredSourceConfiguration.model_validate_json(existing["document_json"])
                    != configuration
                ):
                    raise ValueError("stored source configuration identity has different content")
                return False
            connection.execute(
                """
                INSERT INTO authored_source_configurations(
                    source_configuration_id, project_id, source_alias,
                    spreadsheet_id, configured_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    configuration.source_configuration_id,
                    configuration.project_id,
                    configuration.source_alias,
                    configuration.spreadsheet_id,
                    configuration.configured_at.isoformat(),
                    configuration.model_dump_json(),
                ),
            )
        return True

    def configuration_for_source(
        self, *, project_id: str, source_alias: str, spreadsheet_id: str
    ) -> AuthoredSourceConfiguration | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM authored_source_configurations
                WHERE project_id = ? AND source_alias = ? AND spreadsheet_id = ?
                ORDER BY configured_at, source_configuration_id LIMIT 1
                """,
                (project_id, source_alias, spreadsheet_id),
            ).fetchone()
        return (
            None
            if row is None
            else AuthoredSourceConfiguration.model_validate_json(row["document_json"])
        )

    def record_import(
        self,
        *,
        project_id: str,
        source_configuration_id: str,
        snapshot: AuthoredSourceSnapshot,
        batch: AuthoredImportBatch,
    ) -> bool:
        if batch.source_snapshot_id != snapshot.source_snapshot_id:
            raise ValueError("import batch does not reference its source snapshot")
        if batch.source_snapshot_hash != snapshot.snapshot_hash:
            raise ValueError("import batch source hash does not match its snapshot")
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = AuthoredSourceFetchAttempt(
                fetch_attempt_id=(
                    "source-fetch-"
                    + uuid5(
                        NAMESPACE_URL,
                        f"{source_configuration_id}:{snapshot.fetched_at.isoformat()}:"
                        f"{snapshot.snapshot_hash}",
                    ).hex
                ),
                project_id=project_id,
                source_configuration_id=source_configuration_id,
                fetched_at=snapshot.fetched_at,
                succeeded=True,
                source_snapshot_id=snapshot.source_snapshot_id,
                snapshot_hash=snapshot.snapshot_hash,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO authored_source_fetch_attempts(
                    fetch_attempt_id, project_id, source_configuration_id,
                    fetched_at, succeeded, snapshot_hash, document_json
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    attempt.fetch_attempt_id,
                    project_id,
                    source_configuration_id,
                    attempt.fetched_at.isoformat(),
                    attempt.snapshot_hash,
                    attempt.model_dump_json(),
                ),
            )
            existing_snapshot = connection.execute(
                "SELECT document_json FROM authored_source_snapshots WHERE source_snapshot_id = ?",
                (snapshot.source_snapshot_id,),
            ).fetchone()
            if existing_snapshot is not None:
                existing_batch = connection.execute(
                    "SELECT document_json FROM authored_import_batches "
                    "WHERE source_snapshot_id = ?",
                    (snapshot.source_snapshot_id,),
                ).fetchone()
                stored_snapshot = AuthoredSourceSnapshot.model_validate_json(
                    existing_snapshot["document_json"]
                )
                stored_batch = (
                    None
                    if existing_batch is None
                    else AuthoredImportBatch.model_validate_json(existing_batch["document_json"])
                )
                if (
                    stored_snapshot.model_copy(update={"fetched_at": snapshot.fetched_at})
                    != snapshot
                    or stored_batch is None
                    or stored_batch.model_copy(update={"fetched_at": batch.fetched_at}) != batch
                ):
                    raise ValueError("stored source snapshot identity has different import content")
                return False
            connection.execute(
                """
                INSERT INTO authored_source_snapshots(
                    source_snapshot_id, project_id, source_configuration_id,
                    snapshot_hash, fetched_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.source_snapshot_id,
                    project_id,
                    source_configuration_id,
                    snapshot.snapshot_hash,
                    snapshot.fetched_at.isoformat(),
                    snapshot.model_dump_json(),
                ),
            )
            connection.execute(
                """
                INSERT INTO authored_import_batches(
                    import_batch_id, project_id, source_snapshot_id,
                    normalized_content_hash, valid, fetched_at, document_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.import_batch_id,
                    project_id,
                    snapshot.source_snapshot_id,
                    batch.normalized_content_hash,
                    int(batch.valid),
                    batch.fetched_at.isoformat(),
                    batch.model_dump_json(),
                ),
            )
        return True

    def latest_import(self, project_id: str) -> AuthoredImportBatch | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM authored_import_batches
                WHERE project_id = ? ORDER BY fetched_at DESC, import_batch_id DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return (
            None if row is None else AuthoredImportBatch.model_validate_json(row["document_json"])
        )

    def latest_snapshot(self, project_id: str) -> AuthoredSourceSnapshot | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM authored_source_snapshots
                WHERE project_id = ? ORDER BY fetched_at DESC, source_snapshot_id DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return (
            None
            if row is None
            else AuthoredSourceSnapshot.model_validate_json(row["document_json"])
        )

    def latest_successful_fetch_at(self, project_id: str) -> datetime | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT fetched_at FROM authored_source_fetch_attempts
                WHERE project_id = ? AND succeeded = 1
                ORDER BY fetched_at DESC, fetch_attempt_id DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return None if row is None else datetime.fromisoformat(str(row["fetched_at"]))

    def record_fetch_failure(
        self,
        *,
        project_id: str,
        source_configuration_id: str,
        fetched_at: datetime,
        error_category: str,
    ) -> None:
        attempt = AuthoredSourceFetchAttempt(
            fetch_attempt_id=(
                "source-fetch-"
                + uuid5(
                    NAMESPACE_URL,
                    f"{source_configuration_id}:{fetched_at.isoformat()}:{error_category}",
                ).hex
            ),
            project_id=project_id,
            source_configuration_id=source_configuration_id,
            fetched_at=fetched_at,
            succeeded=False,
            error_category=error_category,
        )
        with self._connection() as connection, connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO authored_source_fetch_attempts(
                    fetch_attempt_id, project_id, source_configuration_id,
                    fetched_at, succeeded, snapshot_hash, document_json
                ) VALUES (?, ?, ?, ?, 0, NULL, ?)
                """,
                (
                    attempt.fetch_attempt_id,
                    project_id,
                    source_configuration_id,
                    fetched_at.isoformat(),
                    attempt.model_dump_json(),
                ),
            )

    def latest_fetch_attempt(self, project_id: str) -> AuthoredSourceFetchAttempt | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM authored_source_fetch_attempts
                WHERE project_id = ? ORDER BY fetched_at DESC, fetch_attempt_id DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return (
            None
            if row is None
            else AuthoredSourceFetchAttempt.model_validate_json(row["document_json"])
        )

    def list_imports(self, project_id: str) -> tuple[AuthoredImportBatch, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT document_json FROM authored_import_batches
                WHERE project_id = ? ORDER BY fetched_at DESC, import_batch_id DESC
                """,
                (project_id,),
            ).fetchall()
        return tuple(AuthoredImportBatch.model_validate_json(row["document_json"]) for row in rows)

    def load_import(self, project_id: str, import_batch_id: str) -> AuthoredImportBatch:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT document_json FROM authored_import_batches "
                "WHERE project_id = ? AND import_batch_id = ?",
                (project_id, import_batch_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown authored import: {import_batch_id}")
        return AuthoredImportBatch.model_validate_json(row["document_json"])

    def load_import_for_snapshot(
        self, project_id: str, source_snapshot_id: str
    ) -> AuthoredImportBatch:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT document_json FROM authored_import_batches "
                "WHERE project_id = ? AND source_snapshot_id = ?",
                (project_id, source_snapshot_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown authored source snapshot: {source_snapshot_id}")
        return AuthoredImportBatch.model_validate_json(row["document_json"])

    def source_configuration_for_import(
        self, project_id: str, import_batch_id: str
    ) -> AuthoredSourceConfiguration:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT c.document_json
                FROM authored_import_batches AS i
                JOIN authored_source_snapshots AS s
                  ON s.source_snapshot_id = i.source_snapshot_id
                JOIN authored_source_configurations AS c
                  ON c.source_configuration_id = s.source_configuration_id
                WHERE i.project_id = ? AND i.import_batch_id = ?
                """,
                (project_id, import_batch_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown authored import: {import_batch_id}")
        return AuthoredSourceConfiguration.model_validate_json(row["document_json"])

    def latest_configuration(self, project_id: str) -> AuthoredSourceConfiguration | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document_json FROM authored_source_configurations
                WHERE project_id = ? ORDER BY configured_at DESC, source_configuration_id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return (
            None
            if row is None
            else AuthoredSourceConfiguration.model_validate_json(row["document_json"])
        )

    def record_bindings(self, bindings: tuple[ExternalIdentityBinding, ...]) -> None:
        """Record immutable unique source-to-canonical identities after acceptance."""

        if not bindings:
            raise ValueError("at least one external identity binding is required")
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for binding in bindings:
                existing = connection.execute(
                    """
                    SELECT document_json FROM external_identity_bindings
                    WHERE project_id = ? AND source_system = ? AND source_instance = ?
                      AND namespace = ? AND external_value = ?
                    """,
                    (
                        binding.project_id,
                        binding.source_system,
                        binding.source_instance,
                        binding.namespace,
                        binding.value,
                    ),
                ).fetchone()
                if existing is not None:
                    stored = ExternalIdentityBinding.model_validate_json(existing["document_json"])
                    if stored.canonical_subject_id != binding.canonical_subject_id:
                        raise ValueError("external identity is already bound to another subject")
                    continue
                connection.execute(
                    """
                    INSERT INTO external_identity_bindings(
                        binding_id, project_id, source_system, source_instance,
                        namespace, external_value, canonical_subject_id,
                        import_batch_id, evidence_reference, accepted_at, document_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        binding.binding_id,
                        binding.project_id,
                        binding.source_system,
                        binding.source_instance,
                        binding.namespace,
                        binding.value,
                        binding.canonical_subject_id,
                        binding.import_batch_id,
                        binding.evidence_reference,
                        binding.accepted_at.isoformat(),
                        binding.model_dump_json(),
                    ),
                )

    def list_bindings(self, project_id: str) -> tuple[ExternalIdentityBinding, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT document_json FROM external_identity_bindings
                WHERE project_id = ?
                ORDER BY source_system, source_instance, namespace, external_value
                """,
                (project_id,),
            ).fetchall()
        return tuple(
            ExternalIdentityBinding.model_validate_json(row["document_json"]) for row in rows
        )
