"""Narrow protocols that keep provider SDK types out of domain code."""

from __future__ import annotations

from typing import Protocol

from reefproof.authored_sources.models import AuthoredSourceSnapshot


class CredentialProvider(Protocol):
    def authorization_headers(self) -> dict[str, str]: ...


class AuthoredSystemSource(Protocol):
    def fetch(self) -> AuthoredSourceSnapshot: ...
