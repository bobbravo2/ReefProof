"""Independent source freshness projection."""

from __future__ import annotations

from datetime import datetime

from reefproof.authored_sources.models import (
    AuthoredSourceConfiguration,
    AuthoredSourceSnapshot,
    AuthoredSourceStatus,
    SourceHealth,
)


def authored_source_status(
    *,
    configuration: AuthoredSourceConfiguration | None,
    latest_snapshot: AuthoredSourceSnapshot | None,
    now: datetime,
    fetch_error: str | None = None,
    accepted_snapshot_hash: str | None = None,
) -> AuthoredSourceStatus:
    if configuration is None:
        return AuthoredSourceStatus(
            health=SourceHealth.NOT_CONFIGURED,
            detail="No authored Google Sheets source is configured.",
        )
    if fetch_error is not None:
        return AuthoredSourceStatus(
            health=SourceHealth.UNAVAILABLE,
            last_successful_fetch_at=(
                None if latest_snapshot is None else latest_snapshot.fetched_at
            ),
            latest_snapshot_hash=(
                None if latest_snapshot is None else latest_snapshot.snapshot_hash
            ),
            detail="The live source fetch failed; retained evidence remains unchanged.",
        )
    if latest_snapshot is None:
        return AuthoredSourceStatus(
            health=SourceHealth.UNAVAILABLE,
            detail="The configured source has no successful fetch evidence.",
        )
    if (
        accepted_snapshot_hash is not None
        and latest_snapshot.snapshot_hash != accepted_snapshot_hash
    ):
        return AuthoredSourceStatus(
            health=SourceHealth.CHANGED,
            last_successful_fetch_at=latest_snapshot.fetched_at,
            latest_snapshot_hash=latest_snapshot.snapshot_hash,
            detail="The latest source differs from accepted authored state and requires review.",
        )
    age = (now - latest_snapshot.fetched_at).total_seconds()
    health = SourceHealth.STALE if age > configuration.freshness_seconds else SourceHealth.CURRENT
    return AuthoredSourceStatus(
        health=health,
        last_successful_fetch_at=latest_snapshot.fetched_at,
        latest_snapshot_hash=latest_snapshot.snapshot_hash,
        detail=(
            "The latest source evidence is outside its freshness policy."
            if health is SourceHealth.STALE
            else "The latest source evidence is within its freshness policy."
        ),
    )
