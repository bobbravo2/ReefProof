"""Narrow alert adapter contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from reefproof.invariants import Severity


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source: str
    title: str
    severity: Severity
    invariant_id: str
    summary: str
    first_seen: datetime
    configuration_hash: str
    policy_hash: str
    affected_entities: tuple[str, ...]
    recommended_action: str
    reefproof_url: str
    recovery: bool


class AlertAdapter(Protocol):
    name: str

    async def send(self, event: AlertEvent) -> None:
        """Deliver one already-deduplicated alert event."""
