"""Durable, identity-bound operator session acceptance authority."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated, Protocol
from uuid import uuid4

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyCookie

SESSION_COOKIE = "reefproof_session"
SESSION_MAX_AGE_SECONDS = 8 * 3600


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session_id: str
    principal: Principal
    issued_at: int


@dataclass(frozen=True, slots=True)
class ActiveSession:
    session_id: str
    principal_id: str
    issued_at: int

    @property
    def display_suffix(self) -> str:
        return self.session_id[-8:]


class OperatorSessionStore(Protocol):
    def record_session(
        self, session_id: str, principal_id: str, issued_at: int, authentication_generation: int
    ) -> None: ...
    def revoke_session(self, session_id: str) -> bool: ...
    def list_sessions(
        self,
        principal_id: str,
        authentication_generation: int,
    ) -> tuple[ActiveSession, ...]: ...


class OperatorSessions:
    """Issue and accept opaque durable IDs for one configured authority."""

    def __init__(
        self,
        bootstrap_secret: str | None,
        *,
        principal_id: str = "local-acceptance-authority",
        principal_display_name: str = "Local acceptance authority",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
        authentication_generation: Callable[[], int] = lambda: 0,
        session_store: OperatorSessionStore | None = None,
        **_legacy: object,
    ) -> None:
        self._bootstrap_secret = bootstrap_secret
        self._principal = Principal(principal_id, principal_display_name)
        self._now = now
        self._max_age_seconds = max_age_seconds
        self._authentication_generation = authentication_generation
        self._session_store = session_store
        self._local_sessions: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    @property
    def configured(self) -> bool:
        return bool(self._bootstrap_secret)

    def create(self, candidate_secret: str) -> str | None:
        if not self.configured or not hmac.compare_digest(
            candidate_secret, self._bootstrap_secret or ""
        ):
            return None
        return self.create_authenticated()

    def create_authenticated(self) -> str:
        session_id = str(uuid4())
        issued_at = int(self._now().timestamp())
        generation = self._authentication_generation()
        with self._lock:
            self._local_sessions[session_id] = (issued_at, generation)
        if self._session_store is not None:
            self._session_store.record_session(
                session_id, self._principal.principal_id, issued_at, generation
            )
        return session_id

    def resolve(self, session_id: str | None) -> AuthenticatedSession | None:
        if not session_id:
            return None
        generation = self._authentication_generation()
        if self._session_store is None:
            with self._lock:
                local_session = self._local_sessions.get(session_id)
            candidates = (
                ()
                if local_session is None or local_session[1] != generation
                else (
                    ActiveSession(
                        session_id,
                        self._principal.principal_id,
                        local_session[0],
                    ),
                )
            )
        else:
            candidates = self._session_store.list_sessions(self._principal.principal_id, generation)
        active = next((item for item in candidates if item.session_id == session_id), None)
        if active is None:
            return None
        age = int(self._now().timestamp()) - active.issued_at
        if age < 0 or age > self._max_age_seconds:
            return None
        return AuthenticatedSession(session_id, self._principal, active.issued_at)

    def principal(self, session_id: str | None) -> Principal | None:
        session = self.resolve(session_id)
        return session.principal if session else None

    def revoke(self, session_id: str | None) -> None:
        if session_id:
            self.revoke_session_id(session_id)

    def active_sessions(self) -> tuple[ActiveSession, ...]:
        generation = self._authentication_generation()
        if self._session_store is not None:
            sessions = list(
                self._session_store.list_sessions(self._principal.principal_id, generation)
            )
        else:
            with self._lock:
                sessions = [
                    ActiveSession(session_id, self._principal.principal_id, issued_at)
                    for session_id, (issued_at, recorded_generation) in self._local_sessions.items()
                    if recorded_generation == generation
                ]
        return tuple(sorted(sessions, key=lambda item: (item.issued_at, item.session_id)))

    def revoke_session_id(self, session_id: str) -> bool:
        if self._session_store is not None:
            return self._session_store.revoke_session(session_id)
        with self._lock:
            return self._local_sessions.pop(session_id, None) is not None


class SessionDependencies:
    """FastAPI security dependencies backed by Starlette request sessions."""

    def __init__(self, registry: OperatorSessions) -> None:
        self._registry = registry
        self._cookie = APIKeyCookie(
            name=SESSION_COOKIE, scheme_name="operatorSession", auto_error=False
        )

    def optional(
        self,
        request: Request,
        _cookie: Annotated[
            str | None,
            Security(
                APIKeyCookie(name=SESSION_COOKIE, scheme_name="operatorSession", auto_error=False)
            ),
        ] = None,
    ) -> AuthenticatedSession | None:
        return self._registry.resolve(request.session.get("session_id"))

    def required(
        self,
        request: Request,
        _cookie: Annotated[
            str | None,
            Security(
                APIKeyCookie(name=SESSION_COOKIE, scheme_name="operatorSession", auto_error=False)
            ),
        ] = None,
    ) -> AuthenticatedSession:
        session = self._registry.resolve(request.session.get("session_id"))
        if session is None:
            raise HTTPException(status_code=401, detail="valid authenticated session required")
        return session
