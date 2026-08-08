"""Authenticated, fixed-purpose operations for a hosted ReefProof service."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask

from reefproof.api.sessions import AuthenticatedSession, OperatorSessions, SessionDependencies
from reefproof.storage import Database

_MAX_ORPHAN_SCAN = 1_000


def _staged_backup_id(path: Path) -> UUID | None:
    prefix = "staged-"
    suffix = ".sqlite3"
    if not path.name.startswith(prefix) or not path.name.endswith(suffix):
        return None
    try:
        identifier = UUID(path.name[len(prefix) : -len(suffix)])
    except ValueError:
        return None
    if identifier.version != 4 or str(identifier) != path.name[len(prefix) : -len(suffix)]:
        return None
    return identifier


def _remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        path.with_name(f"{path.name}{suffix}").unlink(missing_ok=True)


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: str
    detail: str


class DiagnosticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    checks: tuple[DiagnosticCheck, ...]


class HostedBackupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    backup_id: str
    integrity: str
    schema_version: int
    sha256: str


class HostedLifecycleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    operation: str
    detail: str


class HostedOperations(Protocol):
    def diagnostics(self) -> DiagnosticsResponse: ...

    def backup(self) -> HostedBackupResponse: ...

    def claim_backup(self, backup_id: str) -> Path: ...

    def restart(self) -> HostedLifecycleResponse: ...


@dataclass(frozen=True, slots=True)
class _StagedBackup:
    path: Path
    created_at: datetime


class LocalHostedOperations:
    """Execute allowlisted operations against this ReefProof service only."""

    def __init__(
        self,
        *,
        database: Database,
        data_directory: Path,
        backup_directory: Path | None,
        now: Callable[[], datetime],
        restart_service: Callable[[], str] | None = None,
        backup_retention: timedelta = timedelta(hours=24),
    ) -> None:
        self._database = database
        self._data_directory = data_directory
        self._backup_directory = backup_directory
        self._now = now
        self._restart_service = restart_service
        self._backup_retention = backup_retention
        self._backups: dict[str, _StagedBackup] = {}
        self._backup_lock = Lock()
        with self._backup_lock:
            self._expire_backups()

    def _expire_backups(self) -> None:
        cutoff = self._now() - self._backup_retention
        expired = tuple(
            backup_id for backup_id, staged in self._backups.items() if staged.created_at < cutoff
        )
        for backup_id in expired:
            staged = self._backups.pop(backup_id)
            _remove_sqlite_sidecars(staged.path)
            staged.path.unlink(missing_ok=True)
        if self._backup_directory is None or not self._backup_directory.is_dir():
            return
        staged_candidates = sorted(
            candidate
            for candidate in self._backup_directory.iterdir()
            if _staged_backup_id(candidate) is not None
        )[:_MAX_ORPHAN_SCAN]
        for candidate in staged_candidates:
            try:
                expired_on_disk = candidate.stat().st_mtime <= cutoff.timestamp()
            except FileNotFoundError:
                continue
            if expired_on_disk:
                _remove_sqlite_sidecars(candidate)
                candidate.unlink(missing_ok=True)

    def diagnostics(self) -> DiagnosticsResponse:
        with self._backup_lock:
            self._expire_backups()
        checks: list[DiagnosticCheck] = []
        try:
            integrity = self._database.integrity_check()
            schema = self._database.schema_version()
            journal = self._database.journal_mode()
        except (OSError, sqlite3.DatabaseError, ValueError) as error:
            checks.append(DiagnosticCheck(name="evidence store", status="FAIL", detail=str(error)))
        else:
            status = "PASS" if integrity == "ok" and journal.casefold() == "wal" else "FAIL"
            checks.append(
                DiagnosticCheck(
                    name="evidence store",
                    status=status,
                    detail=f"integrity={integrity}; schema={schema}; journal={journal}",
                )
            )
        writable = self._data_directory.is_dir() and self._data_directory.stat().st_mode != 0
        checks.append(
            DiagnosticCheck(
                name="data directory",
                status="PASS" if writable else "FAIL",
                detail="configured hosted data directory is available"
                if writable
                else "configured hosted data directory is unavailable",
            )
        )
        overall = "PASS" if all(check.status == "PASS" for check in checks) else "FAIL"
        return DiagnosticsResponse(status=overall, checks=tuple(checks))

    def backup(self) -> HostedBackupResponse:
        if self._backup_directory is None:
            raise RuntimeError("hosted ReefProof backup directory is not configured")
        root = self._backup_directory.resolve()
        root.mkdir(parents=True, exist_ok=True)
        with self._backup_lock:
            self._expire_backups()
        backup_id = str(uuid4())
        destination = root / f"staged-{uuid4()}.sqlite3"
        try:
            self._database.backup_to(destination)
            backup = Database(destination)
            digest = sha256(destination.read_bytes()).hexdigest()
            response = HostedBackupResponse(
                status="PASS",
                backup_id=backup_id,
                integrity=backup.integrity_check(),
                schema_version=backup.schema_version(),
                sha256=digest,
            )
            timestamp = self._now().timestamp()
            os.utime(destination, (timestamp, timestamp))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            _remove_sqlite_sidecars(destination)
        with self._backup_lock:
            self._backups[backup_id] = _StagedBackup(
                path=destination,
                created_at=self._now(),
            )
        return response

    def restart(self) -> HostedLifecycleResponse:
        with self._backup_lock:
            self._expire_backups()
        if self._restart_service is None:
            raise RuntimeError("hosted ReefProof supervisor is not configured")
        return HostedLifecycleResponse(
            status="ACCEPTED",
            operation="restart",
            detail=self._restart_service(),
        )

    def claim_backup(self, backup_id: str) -> Path:
        if self._backup_directory is None:
            raise RuntimeError("hosted ReefProof backup directory is not configured")
        try:
            parsed = UUID(backup_id)
        except ValueError as error:
            raise ValueError("hosted backup ID must be a UUID") from error
        if parsed.version != 4 or str(parsed) != backup_id:
            raise ValueError("hosted backup ID must be a canonical UUIDv4")
        with self._backup_lock:
            self._expire_backups()
            staged = self._backups.pop(backup_id, None)
            if staged is None or not staged.path.is_file():
                raise FileNotFoundError("hosted backup is expired or already claimed")
            _remove_sqlite_sidecars(staged.path)
            claimed = staged.path.parent / f".claimed-{uuid4()}.download"
            staged.path.replace(claimed)
        return claimed


def register_hosted_operation_routes(
    app: FastAPI,
    *,
    operations: HostedOperations,
    operator_sessions: OperatorSessions,
    session_dependencies: SessionDependencies,
    audit: Callable[..., None],
) -> None:
    required_session = Depends(session_dependencies.required)

    def principal(session: AuthenticatedSession, operation_marker: str | None) -> str:
        if operation_marker != "desktop":
            raise HTTPException(status_code=403, detail="hosted operation marker required")
        return session.principal.principal_id

    @app.get("/v1/operations/diagnostics", response_model=DiagnosticsResponse)
    def diagnostics(
        session: AuthenticatedSession = required_session,
        operation_marker: str | None = Header(default=None, alias="X-ReefProof-Operation"),
    ) -> DiagnosticsResponse:
        actor = principal(session, operation_marker)
        result = operations.diagnostics()
        audit("operator.hosted_diagnostics", principal_id=actor, outcome=result.status)
        return result

    @app.post("/v1/operations/backups", response_model=HostedBackupResponse, status_code=201)
    def backup(
        session: AuthenticatedSession = required_session,
        operation_marker: str | None = Header(default=None, alias="X-ReefProof-Operation"),
    ) -> HostedBackupResponse:
        actor = principal(session, operation_marker)
        try:
            result = operations.backup()
        except (OSError, sqlite3.DatabaseError, ValueError, RuntimeError) as error:
            audit("operator.hosted_backup", principal_id=actor, outcome="FAIL")
            raise HTTPException(status_code=503, detail=str(error)) from error
        audit("operator.hosted_backup", principal_id=actor, outcome=result.status)
        return result

    @app.post("/v1/operations/restart", response_model=HostedLifecycleResponse, status_code=202)
    def restart(
        session: AuthenticatedSession = required_session,
        operation_marker: str | None = Header(default=None, alias="X-ReefProof-Operation"),
    ) -> HostedLifecycleResponse:
        actor = principal(session, operation_marker)
        try:
            result = operations.restart()
        except RuntimeError as error:
            audit("operator.hosted_restart", principal_id=actor, outcome="UNAVAILABLE")
            raise HTTPException(status_code=503, detail=str(error)) from error
        audit("operator.hosted_restart", principal_id=actor, outcome=result.status)
        return result

    @app.post(
        "/v1/operations/backups/{backup_id}/download",
        response_class=FileResponse,
    )
    def download_backup(
        backup_id: str,
        session: AuthenticatedSession = required_session,
        operation_marker: str | None = Header(default=None, alias="X-ReefProof-Operation"),
    ) -> FileResponse:
        actor = principal(session, operation_marker)
        try:
            artifact = operations.claim_backup(backup_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except (FileNotFoundError, RuntimeError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        audit("operator.hosted_backup_download", principal_id=actor, outcome="PASS")
        return FileResponse(
            artifact,
            media_type="application/vnd.sqlite3",
            filename="reefproof-backup.sqlite3",
            background=BackgroundTask(artifact.unlink, missing_ok=True),
        )
