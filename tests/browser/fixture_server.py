"""Loopback-only real ReefProof service for deterministic browser acceptance."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn

import reefproof.api.app as api_app_module
from reefproof.api import create_app
from reefproof.authored_sources import (
    AuthoredSourceSnapshot,
    AuthoredSourceTab,
    SourceTabName,
)
from reefproof.authored_sources.models import SOURCE_TAB_NAMES, source_snapshot_hash
from reefproof.configuration import snapshot_hydros_export
from reefproof.project_state import PROJECT_ID, PROJECT_NAME, Project
from reefproof.project_store import ProjectStore
from reefproof.service import RuntimeState
from reefproof.storage import Database

HOST = "127.0.0.1"
PORT = int(os.environ.get("REEFPROOF_FIXTURE_PORT", "4179"))
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
HASH = f"sha256:{'b' * 64}"


class FixtureTotpState:
    """Accept one conspicuous fixture code while bootstrap login remains available."""

    def __init__(self, _path: Path, *, principal_id: str, now=lambda: NOW) -> None:
        self.principal_id = principal_id
        self._now = now

    @property
    def authentication_generation(self) -> int:
        return 0

    @property
    def enrolled(self) -> bool:
        return False

    def verify(self, code: str) -> datetime:
        if code != "123456":
            raise ValueError("invalid fixture TOTP code")
        return self._now()


class FixtureAuthoredSource:
    def fetch(self) -> AuthoredSourceSnapshot:
        rows = {
            SourceTabName.BOM: (
                ("BOM_ID", "ITEM_NAME", "POWER_DOMAIN_ID"),
                ("BOM-1", "Return pump", "PD-1"),
            ),
            SourceTabName.DOMAINS: (("DOMAIN_ID", "NAME"), ("PD-1", "Main circuit")),
            SourceTabName.POWER: (
                ("POWER_ID", "DOMAIN_ID", "POWER_SUPPLY_ID", "LOCATION"),
                ("PWR-1", "PD-1", "PSU-1", "Cabinet"),
            ),
            SourceTabName.DEVICE_INTERFACES: (
                (
                    "INTERFACE_ID",
                    "DEVICE_ID",
                    "BOM_ID",
                    "POWER_DOMAIN_ID",
                    "PORT_ID",
                    "LOCATION",
                    "CABLE_ID",
                    "FROM_ZONE",
                    "FROM_DEVICE",
                    "FROM_PORT",
                    "TO_ZONE",
                    "TO_DEVICE",
                    "TO_PORT",
                ),
                (
                    "IF-1",
                    "DEV-1",
                    "BOM-1",
                    "PD-1",
                    "PORT-1",
                    "Sump",
                    "CBL-0001",
                    "Cabinet",
                    "Controller",
                    "Output 1",
                    "Sump",
                    "Return Pump",
                    "Power",
                ),
            ),
            SourceTabName.OUTPUTS: (
                ("OUTPUT_ID", "DEVICE_ID", "MODE_ID"),
                ("OUT-1", "DEV-1", "MODE-1"),
            ),
            SourceTabName.MODES: (("MODE_ID", "NAME"), ("MODE-1", "Normal")),
        }
        tabs = tuple(
            AuthoredSourceTab(
                name=name,
                source_range=f"'{name.value}'!A1:ZZ10000",
                rows=rows[name],
            )
            for name in SOURCE_TAB_NAMES
        )
        return AuthoredSourceSnapshot(
            source_snapshot_id="snapshot-browser-first-batch",
            source_alias="primary-design-fixture",
            spreadsheet_id="sheet-browser-fixture",
            spreadsheet_title="Primary Reef Browser Fixture",
            fetched_at=NOW,
            tabs=tabs,
            snapshot_hash=source_snapshot_hash(tabs),
        )


def runtime_state() -> RuntimeState:
    return RuntimeState.model_validate(
        {
            "started_at": NOW - timedelta(minutes=5),
            "operating_mode": "fixture",
            "hydros_connection": "disabled",
            "mqtt_connection": "disabled",
            "last_valid_configuration_at": None,
            "last_configuration_change_at": None,
            "configuration_hash": None,
            "last_evaluation_at": None,
            "last_evaluation_duration_seconds": None,
            "latest_evaluated_configuration_hash": None,
            "policy_loaded": True,
            "policy_hash": HASH,
            "annotation_hash": HASH,
            "storage_writable": True,
            "unrecoverable_transport_failure": None,
            "alert_delivery_state": "healthy",
            "maximum_configuration_age_seconds": 600,
        }
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reefproof-browser-") as temporary_directory:
        state_root = Path(temporary_directory)
        database = Database(state_root / "reefproof.sqlite3")
        database.migrate()
        database.record_snapshot(
            snapshot_hydros_export(
                Path("tests/fixtures/configuration/hydros-download-config-sanitized.json"),
                captured_at=NOW,
            )
        )
        ProjectStore(database.path).ensure_project(
            Project(
                project_id=PROJECT_ID,
                name=PROJECT_NAME,
                acceptance_authority_principal_id="local-acceptance-authority",
                created_at=NOW,
            )
        )
        api_app_module.TotpState = FixtureTotpState
        app = create_app(
            runtime_state=runtime_state,
            database=database,
            now=lambda: NOW,
            bootstrap_secret="browser-fixture-secret",
            totp_path=state_root / "operator-totp.json",
            authored_source=FixtureAuthoredSource(),
        )
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
