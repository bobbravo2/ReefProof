"""Deterministic, offline durable-infrastructure verification."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reefproof.configuration import ConfigurationFixture, ConfigurationSnapshot, snapshot_fixture
from reefproof.invariants import EvaluationRun, evaluate_graph
from reefproof.reliability import build_graph
from reefproof.storage import Database

DATABASE_FILENAME = "reefproof.sqlite3"
SCENARIO_VERSION = "0.1"
UNSAFE_RUN_ID = "1b90d6a0-9d78-4b48-b8c0-000000000001"
SAFE_RUN_ID = "1b90d6a0-9d78-4b48-b8c0-000000000002"
UNSAFE_TIME = datetime.fromisoformat("2026-07-25T12:00:00+00:00")
SAFE_TIME = datetime.fromisoformat("2026-07-25T12:01:00+00:00")


class InfraSmokeReport(BaseModel):
    """Machine-readable result of the bundled synthetic scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scenario: str
    scenario_version: str
    database: str
    schema_version: int
    journal_mode: str
    integrity: str
    evidence_provenance: str
    evidence_source_format: str
    snapshot_hashes: tuple[str, ...]
    evaluation_run_ids: tuple[str, ...]
    evaluation_result_counts: tuple[int, ...]
    transition_count: int
    idempotent: bool


def database_path(data_directory: Path) -> Path:
    """Keep all durable smoke state underneath the configured data directory."""

    return data_directory / DATABASE_FILENAME


def run_infra_smoke(data_directory: Path) -> InfraSmokeReport:
    """Create or verify one stable unsafe-then-recovered fixture scenario.

    The fixed run identifiers make a second invocation a verification pass, not
    a second set of evidence. No transport, credentials, or network client is
    constructed here.
    """

    with _exclusive_lock(data_directory / "infra-smoke.lock"):
        database = Database(database_path(data_directory))
        database.migrate()
        unsafe = _evaluation(_fixture(shared_power=True), UNSAFE_TIME, UNSAFE_RUN_ID)
        safe = _evaluation(_fixture(shared_power=False), SAFE_TIME, SAFE_RUN_ID)
        existing = (
            database.evaluation_exists(UNSAFE_RUN_ID),
            database.evaluation_exists(SAFE_RUN_ID),
        )
        if existing == (False, False):
            database.record_snapshot(unsafe[0])
            database.record_evaluation(unsafe[1])
            database.record_snapshot(safe[0])
            database.record_evaluation(safe[1])
        elif existing != (True, True):
            raise RuntimeError("infra-smoke scenario is incomplete; restore a consistent database")

        _verify_scenario(database, unsafe[0], safe[0], unsafe[1], safe[1])
        return InfraSmokeReport(
            scenario="offline-authored-unsafe-then-recovered",
            scenario_version=SCENARIO_VERSION,
            database=str(database.path),
            schema_version=database.schema_version(),
            journal_mode=database.journal_mode(),
            integrity=database.integrity_check(),
            evidence_provenance="AUTHORED",
            evidence_source_format="synthetic",
            snapshot_hashes=(unsafe[0].snapshot_hash, safe[0].snapshot_hash),
            evaluation_run_ids=(UNSAFE_RUN_ID, SAFE_RUN_ID),
            evaluation_result_counts=(len(unsafe[1].results), len(safe[1].results)),
            transition_count=database.transition_count("RP-CIRC-001"),
            idempotent=True,
        )


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    """Serialize overlapping Linux/macOS infrastructure-smoke processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _evaluation(
    fixture: ConfigurationFixture,
    timestamp: datetime,
    run_id: str,
) -> tuple[ConfigurationSnapshot, EvaluationRun]:
    snapshot = snapshot_fixture(fixture)
    return snapshot, evaluate_graph(
        build_graph(snapshot),
        evaluation_timestamp=timestamp,
        evaluation_run_id=run_id,
    )


def _verify_scenario(
    database: Database,
    unsafe_snapshot: ConfigurationSnapshot,
    safe_snapshot: ConfigurationSnapshot,
    unsafe_run: EvaluationRun,
    safe_run: EvaluationRun,
) -> None:
    if unsafe_snapshot.provenance != "AUTHORED" or safe_snapshot.provenance != "AUTHORED":
        raise RuntimeError("infra-smoke evidence must remain authored")
    for run in (unsafe_run, safe_run):
        if database.evaluation_results(run.evaluation_run_id) != run.results:
            raise RuntimeError("infra-smoke evaluation evidence is missing or malformed")
    if database.transition_count("RP-CIRC-001") != 2:
        raise RuntimeError("infra-smoke finding transitions are incomplete")
    if database.integrity_check() != "ok":
        raise RuntimeError("infra-smoke database integrity check failed")


def _fixture(*, shared_power: bool) -> ConfigurationFixture:
    power_b = "power-a" if shared_power else "power-b"
    captured_at = "2026-07-25T12:00:00+00:00" if shared_power else "2026-07-25T12:01:00+00:00"
    return ConfigurationFixture.model_validate(
        {
            "fixture_version": "0.1",
            "provenance": "AUTHORED",
            "source_format": "synthetic",
            "payload": {
                "captured_at": captured_at,
                "entities": [
                    {
                        "key": "return-a",
                        "vendor_id": "infra-smoke-return-a",
                        "display_name": "Synthetic Return A",
                        "entity_type": "device",
                        "observed_properties": {"enabled": True},
                        "source_path": "$.devices[0]",
                        "confidence": "high",
                        "vendor_extensions": {"synthetic": True},
                    },
                    {
                        "key": "return-b",
                        "vendor_id": "infra-smoke-return-b",
                        "display_name": "Synthetic Return B",
                        "entity_type": "device",
                        "observed_properties": {"enabled": True},
                        "source_path": "$.devices[1]",
                        "confidence": "high",
                        "vendor_extensions": {"synthetic": True},
                    },
                ],
                "authored_entities": [
                    {
                        "key": "power-a",
                        "display_name": "Synthetic Power A",
                        "entity_type": "power_domain",
                        "source": "infra-smoke",
                        "owner": "ReefProof",
                        "last_verified": "2026-07-25",
                        "review_after": "2027-07-25",
                    },
                    {
                        "key": "power-b",
                        "display_name": "Synthetic Power B",
                        "entity_type": "power_domain",
                        "source": "infra-smoke",
                        "owner": "ReefProof",
                        "last_verified": "2026-07-25",
                        "review_after": "2027-07-25",
                    },
                ],
                "annotations": [
                    {
                        "subject_key": "return-a",
                        "relationship": "redundant_with",
                        "target_key": "return-b",
                        "source": "infra-smoke",
                        "owner": "ReefProof",
                        "last_verified": "2026-07-25",
                        "review_after": "2027-07-25",
                    },
                    {
                        "subject_key": "return-a",
                        "relationship": "powered_by",
                        "target_key": "power-a",
                        "source": "infra-smoke",
                        "owner": "ReefProof",
                        "last_verified": "2026-07-25",
                        "review_after": "2027-07-25",
                    },
                    {
                        "subject_key": "return-b",
                        "relationship": "powered_by",
                        "target_key": power_b,
                        "source": "infra-smoke",
                        "owner": "ReefProof",
                        "last_verified": "2026-07-25",
                        "review_after": "2027-07-25",
                    },
                ],
                "vendor_extensions": {
                    "synthetic_notice": (
                        "Bundled authored infrastructure smoke data; never live HYDROS."
                    )
                },
            },
        }
    )
