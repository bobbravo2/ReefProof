"""Zero-trust browser-session boundary tests."""

from datetime import UTC, datetime, timedelta

from reefproof.api.sessions import ActiveSession, OperatorSessions

NOW = datetime(2026, 7, 25, 20, tzinfo=UTC)


def test_opaque_session_id_is_identity_bound_and_revocable() -> None:
    sessions = OperatorSessions(
        "configured-factor",
        principal_id="configured-authority",
        principal_display_name="Configured authority",
        now=lambda: NOW,
    )

    assert sessions.create("wrong-factor") is None
    session_id = sessions.create("configured-factor")
    assert session_id is not None
    resolved = sessions.resolve(session_id)
    assert resolved is not None
    assert resolved.principal.principal_id == "configured-authority"
    assert resolved.principal.display_name == "Configured authority"

    assert "configured-authority" not in session_id
    assert sessions.resolve(f"{session_id}tampered") is None

    sessions.revoke(session_id)
    assert sessions.resolve(session_id) is None


def test_session_registry_expires_at_the_configured_browser_edge() -> None:
    current = NOW
    sessions = OperatorSessions(
        "configured-factor",
        now=lambda: current,
        max_age_seconds=60,
    )
    cookie = sessions.create("configured-factor")
    assert cookie is not None

    current += timedelta(seconds=61)
    assert sessions.resolve(cookie) is None


class _MemorySessionStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, int, int, bool]] = {}

    def record_session(
        self,
        session_id: str,
        principal_id: str,
        issued_at: int,
        authentication_generation: int,
    ) -> None:
        self._rows[session_id] = (principal_id, issued_at, authentication_generation, False)

    def has_session(
        self,
        session_id: str,
        principal_id: str,
        authentication_generation: int,
    ) -> bool:
        row = self._rows.get(session_id)
        if row is None:
            return False
        stored_principal_id, _issued_at, stored_generation, revoked = row
        return (
            stored_principal_id == principal_id
            and stored_generation == authentication_generation
            and not revoked
        )

    def revoke_session(self, session_id: str) -> bool:
        row = self._rows.get(session_id)
        if row is None:
            return False
        principal_id, issued_at, generation, revoked = row
        if revoked:
            return False
        self._rows[session_id] = (principal_id, issued_at, generation, True)
        return True

    def list_sessions(
        self,
        principal_id: str,
        authentication_generation: int,
    ) -> tuple[ActiveSession, ...]:
        sessions = [
            ActiveSession(
                session_id=session_id,
                principal_id=stored_principal_id,
                issued_at=issued_at,
            )
            for session_id, (
                stored_principal_id,
                issued_at,
                stored_generation,
                revoked,
            ) in self._rows.items()
            if (
                stored_principal_id == principal_id
                and stored_generation == authentication_generation
                and not revoked
            )
        ]
        sessions.sort(key=lambda session: (session.issued_at, session.session_id))
        return tuple(sessions)


def test_active_sessions_can_be_listed_and_revoked_by_session_id() -> None:
    store = _MemorySessionStore()
    sessions = OperatorSessions(
        "configured-factor",
        principal_id="configured-authority",
        principal_display_name="Configured authority",
        now=lambda: NOW,
        session_store=store,
    )
    first = sessions.create("configured-factor")
    second = sessions.create("configured-factor")
    assert first is not None
    assert second is not None

    active = sessions.active_sessions()
    assert len(active) == 2
    assert all(session.principal_id == "configured-authority" for session in active)

    revoked = sessions.revoke_session_id(active[0].session_id)
    assert revoked is True
    remaining = sessions.active_sessions()
    assert len(remaining) == 1
    assert remaining[0].session_id == active[1].session_id


def test_store_revocation_is_visible_to_other_process_instances() -> None:
    store = _MemorySessionStore()
    primary = OperatorSessions(
        "configured-factor",
        principal_id="configured-authority",
        principal_display_name="Configured authority",
        now=lambda: NOW,
        session_store=store,
    )
    cookie = primary.create("configured-factor")
    assert cookie is not None
    session = primary.resolve(cookie)
    assert session is not None

    secondary = OperatorSessions(
        "configured-factor",
        principal_id="configured-authority",
        principal_display_name="Configured authority",
        now=lambda: NOW,
        session_store=store,
    )
    assert secondary.revoke_session_id(session.session_id) is True
    assert primary.resolve(cookie) is None
