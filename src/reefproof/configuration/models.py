"""Typed canonical configuration and annotation evidence."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class EntityType(StrEnum):
    CONTROLLER = "controller"
    PORT = "port"
    INPUT = "input"
    SENSOR = "sensor"
    OUTPUT = "output"
    DEVICE = "device"
    MODE = "mode"
    SCHEDULE = "schedule"
    COMBINER = "combiner"
    FUNCTION = "function"
    ZONE = "zone"
    POWER_DOMAIN = "power_domain"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    OWNS = "owns"
    DRIVES = "drives"
    POWERS = "powers"
    SERVES = "serves"
    LOCATED_IN = "located_in"
    POWERED_BY = "powered_by"
    CONTROLLED_BY = "controlled_by"
    ACTIVE_IN = "active_in"
    DEPENDS_ON = "depends_on"
    CONSUMES = "consumes"
    MEASURES = "measures"
    PROTECTS = "protects"
    REDUNDANT_WITH = "redundant_with"
    REQUIRED_FOR = "required_for"
    HAS_PROPERTY = "has_property"


class ConfigurationFixture(BaseModel):
    """A repository-authored fixture, not an observed device export."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    fixture_version: Literal["0.1"]
    provenance: Literal["AUTHORED"]
    source_format: Literal["synthetic"]
    payload: dict[str, JsonValue]


class ObservedEntity(BaseModel):
    """One normalized fact-bearing entity from the observed source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reefproof_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    vendor_id: str | None
    display_name: str = Field(min_length=1)
    entity_type: EntityType
    observed_properties: dict[str, JsonValue]
    source_path: str = Field(min_length=1)
    captured_at: datetime
    raw_configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    confidence: Confidence
    vendor_extensions: dict[str, JsonValue]

    @model_validator(mode="after")
    def captured_at_must_be_timezone_aware(self) -> ObservedEntity:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return self


class AuthoredEntity(BaseModel):
    """A human-defined entity that the vendor source cannot establish."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reefproof_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    display_name: str = Field(min_length=1)
    entity_type: EntityType
    source: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    last_verified: date
    review_after: date | None = None

    @model_validator(mode="after")
    def review_cannot_precede_verification(self) -> AuthoredEntity:
        if self.review_after is not None and self.review_after < self.last_verified:
            raise ValueError("review_after cannot precede last_verified")
        return self


class SystemAnnotation(BaseModel):
    """A human-authored fact kept separate from observed vendor state."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    annotation_id: str = Field(pattern=r"^RP\.ANNOTATION\.[0-9a-f]{16}$")
    subject_id: str = Field(pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$")
    relationship: RelationshipType
    target_id: str | None = Field(
        default=None,
        pattern=r"^RP\.[A-Z_]+\.[0-9a-f]{16}$",
    )
    value: JsonValue = None
    source: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    last_verified: date
    review_after: date | None = None

    @model_validator(mode="after")
    def target_or_value_is_required(self) -> SystemAnnotation:
        if self.target_id is None and self.value is None:
            raise ValueError("annotation requires target_id or value")
        if self.target_id is not None and self.value is not None:
            raise ValueError("annotation cannot contain both target_id and value")
        if self.review_after is not None and self.review_after < self.last_verified:
            raise ValueError("review_after cannot precede last_verified")
        return self


class ConfigurationSnapshot(BaseModel):
    """Deterministic canonical evidence derived from one validated fixture."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_version: Literal["0.1"] = "0.1"
    provenance: Literal["AUTHORED", "OBSERVED"] = "AUTHORED"
    source_format: Literal["synthetic", "hydros_chrome_download_config"] = "synthetic"
    captured_at: datetime
    configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    annotation_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entities: tuple[ObservedEntity, ...]
    authored_entities: tuple[AuthoredEntity, ...]
    annotations: tuple[SystemAnnotation, ...]
    vendor_extensions: dict[str, JsonValue]
    completeness_warnings: tuple[str, ...]

    @model_validator(mode="after")
    def captured_at_must_be_timezone_aware(self) -> ConfigurationSnapshot:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        return self
