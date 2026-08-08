"""Normalize authored fixtures into a vendor-neutral canonical snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from reefproof.configuration.models import (
    AuthoredEntity,
    Confidence,
    ConfigurationFixture,
    ConfigurationSnapshot,
    EntityType,
    ObservedEntity,
    RelationshipType,
    SystemAnnotation,
)
from reefproof.configuration.stable_ids import stable_annotation_id, stable_entity_id


class _FixtureEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    vendor_id: str | None = None
    display_name: str
    entity_type: EntityType
    observed_properties: dict[str, JsonValue]
    source_path: str
    confidence: Confidence
    vendor_extensions: dict[str, JsonValue] = Field(default_factory=dict)


class _FixtureAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject_key: str
    relationship: RelationshipType
    target_key: str | None = None
    value: JsonValue = None
    source: str
    owner: str
    last_verified: date
    review_after: date | None = None

    @model_validator(mode="after")
    def target_or_value_is_required(self) -> _FixtureAnnotation:
        if self.target_key is None and self.value is None:
            raise ValueError("fixture annotation requires target_key or value")
        if self.target_key is not None and self.value is not None:
            raise ValueError("fixture annotation cannot contain both target_key and value")
        return self


class _FixtureAuthoredEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    display_name: str
    entity_type: EntityType
    source: str
    owner: str
    last_verified: date
    review_after: date | None = None


class _FixturePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    captured_at: datetime
    entities: tuple[_FixtureEntity, ...]
    authored_entities: tuple[_FixtureAuthoredEntity, ...] = ()
    annotations: tuple[_FixtureAnnotation, ...] = ()
    vendor_extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_fixture_identity(self) -> _FixturePayload:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a timezone")
        keys = [entity.key for entity in self.entities]
        keys.extend(entity.key for entity in self.authored_entities)
        if len(keys) != len(set(keys)):
            raise ValueError("fixture entity keys must be unique")
        known = set(keys)
        for annotation in self.annotations:
            if annotation.subject_key not in known:
                raise ValueError(f"unknown annotation subject_key: {annotation.subject_key}")
            if annotation.target_key is not None and annotation.target_key not in known:
                raise ValueError(f"unknown annotation target_key: {annotation.target_key}")
        return self


def _jsonable(value: Any) -> JsonValue:
    serialized = json.dumps(
        value,
        default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else str(item),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return json.loads(serialized)


def canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def content_hash(value: JsonValue) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(value)).hexdigest()}"


def normalize_fixture(fixture: ConfigurationFixture) -> ConfigurationSnapshot:
    """Create deterministic canonical entities and separate authored annotations."""

    payload = _FixturePayload.model_validate(fixture.payload)
    ordered_sources = sorted(
        payload.entities,
        key=lambda source: stable_entity_id(
            entity_type=source.entity_type,
            vendor_id=source.vendor_id,
            source_path=source.source_path,
        ),
    )
    raw_entities = _jsonable(
        [entity.model_dump(mode="json", exclude={"key"}) for entity in ordered_sources]
    )
    configuration_hash = content_hash(raw_entities)

    entities_by_key: dict[str, ObservedEntity] = {}
    for source in payload.entities:
        reefproof_id = stable_entity_id(
            entity_type=source.entity_type,
            vendor_id=source.vendor_id,
            source_path=source.source_path,
        )
        entity = ObservedEntity(
            reefproof_id=reefproof_id,
            vendor_id=source.vendor_id,
            display_name=source.display_name,
            entity_type=source.entity_type,
            observed_properties=source.observed_properties,
            source_path=source.source_path,
            captured_at=payload.captured_at,
            raw_configuration_hash=configuration_hash,
            confidence=source.confidence,
            vendor_extensions=source.vendor_extensions,
        )
        if entity.reefproof_id in {item.reefproof_id for item in entities_by_key.values()}:
            raise ValueError(f"stable entity ID collision: {entity.reefproof_id}")
        entities_by_key[source.key] = entity

    authored_by_key: dict[str, AuthoredEntity] = {}
    for source in payload.authored_entities:
        reefproof_id = stable_entity_id(
            entity_type=source.entity_type,
            vendor_id=None,
            source_path=f"authored:{source.key}",
        )
        authored_by_key[source.key] = AuthoredEntity(
            reefproof_id=reefproof_id,
            display_name=source.display_name,
            entity_type=source.entity_type,
            source=source.source,
            owner=source.owner,
            last_verified=source.last_verified,
            review_after=source.review_after,
        )

    all_ids_by_key = {
        **{key: entity.reefproof_id for key, entity in entities_by_key.items()},
        **{key: entity.reefproof_id for key, entity in authored_by_key.items()},
    }

    annotations: list[SystemAnnotation] = []
    for source in payload.annotations:
        subject_id = all_ids_by_key[source.subject_key]
        target_id = all_ids_by_key[source.target_key] if source.target_key is not None else None
        identity = _jsonable(
            {
                "subject_id": subject_id,
                "relationship": source.relationship,
                "target_id": target_id,
                "value": source.value,
                "source": source.source,
                "owner": source.owner,
            }
        )
        annotation = SystemAnnotation(
            annotation_id=stable_annotation_id(canonical_identity=canonical_json(identity)),
            subject_id=subject_id,
            relationship=source.relationship,
            target_id=target_id,
            value=source.value,
            source=source.source,
            owner=source.owner,
            last_verified=source.last_verified,
            review_after=source.review_after,
        )
        annotations.append(annotation)

    ordered_authored = tuple(sorted(authored_by_key.values(), key=lambda item: item.reefproof_id))
    ordered_annotations = tuple(sorted(annotations, key=lambda item: item.annotation_id))
    canonical_annotations = _jsonable(
        {
            "authored_entities": [entity.model_dump(mode="json") for entity in ordered_authored],
            "annotations": [
                annotation.model_dump(mode="json") for annotation in ordered_annotations
            ],
        }
    )
    annotation_hash = content_hash(canonical_annotations)
    ordered_entities = tuple(sorted(entities_by_key.values(), key=lambda item: item.reefproof_id))
    snapshot_content = _jsonable(
        {
            "captured_at": payload.captured_at,
            "configuration_hash": configuration_hash,
            "annotation_hash": annotation_hash,
            "entities": [entity.model_dump(mode="json") for entity in ordered_entities],
            "authored_entities": [entity.model_dump(mode="json") for entity in ordered_authored],
            "annotations": [
                annotation.model_dump(mode="json") for annotation in ordered_annotations
            ],
            "vendor_extensions": payload.vendor_extensions,
        }
    )

    warnings: list[str] = []
    if payload.vendor_extensions:
        warnings.append("Unmodeled fixture-level vendor extensions are preserved.")
    if any(entity.confidence is Confidence.UNKNOWN for entity in ordered_entities):
        warnings.append("One or more observed entities have unknown confidence.")

    return ConfigurationSnapshot(
        captured_at=payload.captured_at,
        configuration_hash=configuration_hash,
        annotation_hash=annotation_hash,
        snapshot_hash=content_hash(snapshot_content),
        entities=ordered_entities,
        authored_entities=ordered_authored,
        annotations=ordered_annotations,
        vendor_extensions=payload.vendor_extensions,
        completeness_warnings=tuple(warnings),
    )
