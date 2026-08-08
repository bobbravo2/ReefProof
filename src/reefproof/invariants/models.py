"""Invariant result contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvariantState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class InvariantResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    invariant_id: str = Field(pattern=r"^RP-[A-Z]+-[0-9]{3}$")
    version: str = Field(min_length=1)
    severity: Severity
    state: InvariantState
    summary: str = Field(min_length=1)
    detailed_explanation: str = Field(min_length=1)
    affected_entities: tuple[str, ...]
    evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    recommended_operator_action: str = Field(min_length=1)
    evaluation_timestamp: datetime
    configuration_hash: str = Field(pattern=r"^(?:UNKNOWN|sha256:[0-9a-f]{64})$")
    annotation_hash: str = Field(pattern=r"^(?:UNKNOWN|sha256:[0-9a-f]{64})$")
    policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evaluation_run_id: str = Field(pattern=r"^[0-9a-f-]{36}$")

    @model_validator(mode="after")
    def validate_result_evidence(self) -> InvariantResult:
        if self.evaluation_timestamp.tzinfo is None:
            raise ValueError("evaluation_timestamp must include a timezone")
        if self.state is InvariantState.UNKNOWN and not self.missing_evidence:
            raise ValueError("UNKNOWN result requires missing_evidence")
        if self.state is not InvariantState.UNKNOWN and self.missing_evidence:
            raise ValueError("only UNKNOWN results may contain missing_evidence")
        return self
