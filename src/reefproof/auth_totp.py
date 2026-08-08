"""File-backed TOTP enrollment and replay protection outside SQLite backups."""

from __future__ import annotations

import base64
import io
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, TypedDict, cast
from uuid import uuid4

import pyotp
import qrcode


class _StateDocument(TypedDict):
    secret: str
    enrolled: bool
    authentication_generation: int
    last_accepted_counter: int | None


class TotpState:
    def __init__(
        self,
        path: Path,
        *,
        principal_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.path = path
        self.principal_id = principal_id
        self._now = now
        self._lock = Lock()
        self._challenges: dict[str, datetime] = {}
        if not path.exists():
            self._write(
                {
                    "secret": pyotp.random_base32(),
                    "enrolled": False,
                    "authentication_generation": 0,
                    "last_accepted_counter": None,
                }
            )

    @property
    def authentication_generation(self) -> int:
        return int(self._read()["authentication_generation"])

    @property
    def enrolled(self) -> bool:
        return bool(self._read()["enrolled"])

    def enrollment(self) -> tuple[str, str]:
        with self._lock:
            state = self._read()
            if state["enrolled"]:
                raise ValueError("TOTP is already enrolled")
            challenge_id = str(uuid4())
            self._challenges[challenge_id] = self._now() + timedelta(minutes=10)
            uri = pyotp.TOTP(str(state["secret"])).provisioning_uri(
                name=self.principal_id,
                issuer_name="ReefProof",
            )
            image = qrcode.make(uri)
            output = io.BytesIO()
            cast(Any, image).save(output, format="PNG")
            return challenge_id, base64.b64encode(output.getvalue()).decode()

    def confirm(self, challenge_id: str, code: str) -> datetime:
        with self._lock:
            deadline = self._challenges.pop(challenge_id, None)
            if deadline is None or self._now() > deadline:
                raise ValueError("enrollment challenge is invalid or expired")
            verified_at, counter = self._verify(self._read(), code)
            state = self._read()
            state["enrolled"] = True
            state["last_accepted_counter"] = counter
            self._write(state)
            self._challenges.clear()
            return verified_at

    def verify(self, code: str) -> datetime:
        with self._lock:
            state = self._read()
            if not state["enrolled"]:
                raise ValueError("TOTP enrollment required")
            verified_at, counter = self._verify(state, code)
            state["last_accepted_counter"] = counter
            self._write(state)
            return verified_at

    def reset(self) -> None:
        with self._lock:
            generation = int(self._read()["authentication_generation"]) + 1
            self._write(
                {
                    "secret": pyotp.random_base32(),
                    "enrolled": False,
                    "authentication_generation": generation,
                    "last_accepted_counter": None,
                }
            )
            self._challenges.clear()

    def _verify(self, state: _StateDocument, code: str) -> tuple[datetime, int]:
        if len(code) != 6 or not code.isdigit():
            raise ValueError("invalid TOTP code")
        now = self._now()
        interval = 30
        current = int(now.timestamp()) // interval
        totp = pyotp.TOTP(str(state["secret"]), interval=interval, digits=6)
        accepted = next(
            (
                counter
                for counter in range(current - 1, current + 2)
                if totp.at(counter * interval) == code
            ),
            None,
        )
        last = state["last_accepted_counter"]
        if accepted is None or (last is not None and accepted <= int(last)):
            raise ValueError("invalid or replayed TOTP code")
        return now, accepted

    def _read(self) -> _StateDocument:
        return cast(_StateDocument, json.loads(self.path.read_text(encoding="utf-8")))

    def _write(self, state: _StateDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)
