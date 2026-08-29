"""Immutable source evidence and normalized import models."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourceTabName(StrEnum):
    BOM = "BOM"
    DOMAINS = "DOMAINS"
    POWER = "POWER"
    DEVICE_INTERFACES = "DEVICE_INTERFACES"
    OUTPUTS = "OUTPUTS"
    MODES = "MODES"


SOURCE_TAB_NAMES = tuple(SourceTabName)


class AuthoredSourceConfiguration(_FrozenModel):
    source_configuration_id: str
    project_id: str
    source_alias: str
    spreadsheet_id: str
    configured_at: datetime
    freshness_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.configured_at.utcoffset() is None:
            raise ValueError("source configuration timestamp must be timezone-aware")
        return self


class AuthoredSourceTab(_FrozenModel):
    name: SourceTabName
    source_range: str
    rows: tuple[tuple[str, ...], ...]


class AuthoredSourceSnapshot(_FrozenModel):
    source_snapshot_id: str
    source_alias: str
    spreadsheet_id: str
    spreadsheet_title: str
    fetched_at: datetime
    provider_version: str | None = None
    tabs: tuple[AuthoredSourceTab, ...]
    snapshot_hash: str

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if self.fetched_at.utcoffset() is None:
            raise ValueError("source fetch timestamp must be timezone-aware")
        names = tuple(tab.name for tab in self.tabs)
        if names != SOURCE_TAB_NAMES:
            raise ValueError("source snapshot must contain the six tabs in canonical order")
        if self.snapshot_hash != source_snapshot_hash(self.tabs):
            raise ValueError("source snapshot hash does not match selected cells")
        return self


class DiagnosticSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class SourceHealth(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    CHANGED = "CHANGED"


class AuthoredSourceStatus(_FrozenModel):
    health: SourceHealth
    last_successful_fetch_at: datetime | None = None
    latest_snapshot_hash: str | None = None
    detail: str


class AuthoredSourceFetchAttempt(_FrozenModel):
    fetch_attempt_id: str
    project_id: str
    source_configuration_id: str
    fetched_at: datetime
    succeeded: bool
    source_snapshot_id: str | None = None
    snapshot_hash: str | None = None
    error_category: str | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> AuthoredSourceFetchAttempt:
        if self.fetched_at.utcoffset() is None:
            raise ValueError("source fetch attempt timestamp must be timezone-aware")
        if self.succeeded != (
            self.source_snapshot_id is not None and self.snapshot_hash is not None
        ):
            raise ValueError("successful fetch attempts require snapshot identity and hash")
        if self.succeeded and self.error_category is not None:
            raise ValueError("successful fetch attempts cannot contain an error category")
        if not self.succeeded and not self.error_category:
            raise ValueError("failed fetch attempts require a bounded error category")
        return self


class ImportDiagnostic(_FrozenModel):
    code: str
    severity: DiagnosticSeverity
    tab: SourceTabName
    source_range: str
    message: str


class SourceProvenance(_FrozenModel):
    tab: SourceTabName
    row_number: int = Field(ge=2)
    source_range: str


class NormalizedSourceRecord(_FrozenModel):
    tab: SourceTabName
    external_namespace: str
    external_id: str
    fields: tuple[tuple[str, str], ...]
    provenance: SourceProvenance


class AuthoredImportBatch(_FrozenModel):
    import_batch_id: str
    source_snapshot_id: str
    source_snapshot_hash: str
    fetched_at: datetime
    parser_schema_version: str = "sheets-v1"
    normalized_content_hash: str
    records: tuple[NormalizedSourceRecord, ...]
    record_counts: dict[SourceTabName, int]
    diagnostics: tuple[ImportDiagnostic, ...]

    @property
    def valid(self) -> bool:
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)


def source_snapshot_hash(tabs: tuple[AuthoredSourceTab, ...]) -> str:
    payload = [
        {"name": tab.name.value, "range": tab.source_range, "rows": tab.rows} for tab in tabs
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def normalized_content_hash(records: tuple[NormalizedSourceRecord, ...]) -> str:
    payload = [record.model_dump(mode="json") for record in records]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"
