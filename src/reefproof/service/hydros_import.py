"""Persist one offline HYDROS export and its operator-confirmed unit check."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reefproof.configuration import ConfigurationSnapshot, snapshot_hydros_export
from reefproof.configuration.hydros import TEMPERATURE_FORMAT_SOURCE_PATH
from reefproof.invariants import EvaluationRun, InvariantResult, InvariantState, Severity
from reefproof.storage import Database


class HydrosImportRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot: ConfigurationSnapshot
    evaluation: EvaluationRun
    snapshot_inserted: bool


def import_hydros_export(
    path: Path,
    *,
    captured_at: datetime,
    expected_temperature_unit: str,
    database: Database,
    evaluation_timestamp: datetime,
    evaluation_run_id: str | None = None,
) -> HydrosImportRun:
    """Run the shared, offline snapshot-plus-evaluation persistence operation."""

    if expected_temperature_unit != "fahrenheit":
        raise ValueError("only the operator-confirmed expected unit 'fahrenheit' is supported")
    snapshot = snapshot_hydros_export(path, captured_at=captured_at)
    system = next(
        (entity for entity in snapshot.entities if entity.entity_type == "controller"),
        None,
    )
    observed = system.observed_properties.get("temperature_display_unit") if system else None
    matched = isinstance(observed, dict) and observed.get("value") == expected_temperature_unit
    run_id = evaluation_run_id or str(uuid.uuid4())
    policy = {
        "invariant_id": "RP-UNIT-001",
        "version": "1",
        "expected_temperature_unit": expected_temperature_unit,
    }
    policy_hash = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    state = InvariantState.PASS if matched else InvariantState.UNKNOWN
    result = InvariantResult(
        invariant_id="RP-UNIT-001",
        version="1",
        severity=Severity.INFO,
        state=state,
        summary=(
            "HYDROS temperature display format is Fahrenheit."
            if matched
            else "HYDROS temperature display format could not be confirmed."
        ),
        detailed_explanation=(
            "The observed HYDROS value 1 matches the operator-confirmed expected "
            "temperature display unit, Fahrenheit."
            if matched
            else "The export did not contain the validated HYDROS value 1 at the known path."
        ),
        affected_entities=(system.reefproof_id,) if system else (),
        evidence=(f'{TEMPERATURE_FORMAT_SOURCE_PATH} = "1"',) if matched else (),
        missing_evidence=() if matched else (f"Value 1 at {TEMPERATURE_FORMAT_SOURCE_PATH}.",),
        recommended_operator_action=(
            "No action required; re-evaluate after changing HYDROS display units."
            if matched
            else "Confirm the temperature display format in HYDROS Device Settings."
        ),
        evaluation_timestamp=evaluation_timestamp,
        configuration_hash=snapshot.configuration_hash,
        annotation_hash=snapshot.annotation_hash,
        policy_hash=policy_hash,
        evaluation_run_id=run_id,
    )
    evaluation = EvaluationRun(
        evaluation_run_id=run_id,
        evaluation_timestamp=evaluation_timestamp,
        policy_hash=policy_hash,
        results=(result,),
    )
    snapshot_inserted = database.record_snapshot(snapshot)
    database.record_evaluation(evaluation)
    return HydrosImportRun(
        snapshot=snapshot,
        evaluation=evaluation,
        snapshot_inserted=snapshot_inserted,
    )
