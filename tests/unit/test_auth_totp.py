from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pyotp
import pytest

from reefproof.api.sessions import OperatorSessions
from reefproof.auth_totp import TotpState

NOW = datetime(2026, 7, 25, 20, 0, 5, tzinfo=UTC)


def _code(path: Path, timestamp: datetime = NOW) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    return pyotp.TOTP(document["secret"]).at(timestamp)


def test_totp_enrollment_is_mode_0600_and_rejects_replay(tmp_path: Path) -> None:
    path = tmp_path / "operator-totp.json"
    state = TotpState(path, principal_id="acceptance-authority", now=lambda: NOW)
    challenge, qr = state.enrollment()
    assert qr.startswith("iVBOR")
    state.confirm(challenge, _code(path))
    assert state.enrolled
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="replayed"):
        state.verify(_code(path))


def test_totp_reset_rotates_generation_and_invalidates_sessions(tmp_path: Path) -> None:
    state = TotpState(
        tmp_path / "operator-totp.json",
        principal_id="acceptance-authority",
        now=lambda: NOW,
    )
    sessions = OperatorSessions(
        "token",
        principal_id="acceptance-authority",
        now=lambda: NOW,
        authentication_generation=lambda: state.authentication_generation,
    )
    cookie = sessions.create("token")
    assert sessions.principal(cookie) is not None
    state.reset()
    assert sessions.principal(cookie) is None
    assert not state.enrolled
