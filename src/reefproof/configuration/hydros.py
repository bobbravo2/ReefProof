"""Offline normalization of HYDROS Chrome Download Config exports."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import JsonValue

from reefproof.configuration.models import (
    Confidence,
    ConfigurationSnapshot,
    EntityType,
    ObservedEntity,
)
from reefproof.configuration.normalize import _jsonable, content_hash
from reefproof.configuration.stable_ids import stable_entity_id

_ENTITY_SECTIONS: dict[str, EntityType] = {
    "System": EntityType.CONTROLLER,
    "Device": EntityType.DEVICE,
    "Input": EntityType.INPUT,
    "Output": EntityType.OUTPUT,
    "Mode": EntityType.MODE,
    "Schedule": EntityType.SCHEDULE,
    "TpDevice": EntityType.DEVICE,
    "WiFiOutlet": EntityType.OUTPUT,
}
_EXPECTED_SECTIONS = frozenset((*_ENTITY_SECTIONS, "Option"))
TEMPERATURE_FORMAT_SOURCE_PATH = '$.Option["Option"].tempFmt'

_SAFE_VENDOR_FIELDS: dict[str, frozenset[str]] = {
    "System": frozenset({"friendlyName", "thingType", "type"}),
    "Device": frozenset({"device", "friendlyName", "thingType", "type"}),
    "Input": frozenset({"senseMode", "sensePort", "type"}),
    "Output": frozenset({"dependency", "outputDevice", "type"}),
    "Mode": frozenset({"readOnly", "type"}),
    "Schedule": frozenset({"type"}),
    "TpDevice": frozenset({"friendlyName", "type"}),
    "WiFiOutlet": frozenset({"friendlyName", "outlet", "type"}),
    "Option": frozenset({"tempFmt", "type"}),
}

_CREDENTIAL_KEYS = frozenset(
    {"apikey", "key", "localkey", "password", "secret", "token", "wifipassword"}
)
_ACCOUNT_IDENTIFIER_KEYS = frozenset({"accountid", "thingname"})
_DEVICE_IDENTIFIER_KEYS = frozenset({"deviceid", "guid", "serialnum", "unitid"})
_NETWORK_IDENTIFIER_KEYS = frozenset({"ip", "ipaddress", "mac", "ssid"})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _vendor_id(document: dict[str, JsonValue]) -> str | None:
    for key in ("guid", "id", "serialNum", "thingName"):
        value = document.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
    return None


def _redaction_category(key: str) -> str:
    normalized = key.casefold().replace("_", "").replace("-", "")
    if normalized in _CREDENTIAL_KEYS or any(
        marker in normalized for marker in ("password", "secret", "token")
    ):
        return "credential"
    if normalized in _ACCOUNT_IDENTIFIER_KEYS or "account" in normalized:
        return "account_identifier"
    if normalized in _NETWORK_IDENTIFIER_KEYS:
        return "network_identifier"
    if normalized in _DEVICE_IDENTIFIER_KEYS or normalized.endswith("id"):
        return "device_identifier"
    return "unallowlisted_vendor_field"


def _redacted_leaves(value: JsonValue, *, path: str, key: str) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        leaves: list[tuple[str, str]] = []
        for child_key, child_value in value.items():
            leaves.extend(
                _redacted_leaves(
                    child_value,
                    path=f"{path}.{child_key}",
                    key=child_key,
                )
            )
        return leaves or [(path, _redaction_category(key))]
    if isinstance(value, list):
        leaves = []
        for index, child_value in enumerate(value):
            leaves.extend(_redacted_leaves(child_value, path=f"{path}[{index}]", key=key))
        return leaves or [(path, _redaction_category(key))]
    return [(path, _redaction_category(key))]


def _safe_vendor_projection(
    section: str,
    record: dict[str, JsonValue],
    *,
    source_path: str,
) -> tuple[dict[str, JsonValue], list[tuple[str, str]]]:
    allowed = _SAFE_VENDOR_FIELDS[section]
    safe: dict[str, JsonValue] = {}
    redacted: list[tuple[str, str]] = []
    for key, value in record.items():
        if key in allowed:
            safe[key] = value
            continue
        redacted.extend(_redacted_leaves(value, path=f"{source_path}.{key}", key=key))
    return safe, redacted


def load_hydros_export(path: Path) -> tuple[dict[str, JsonValue], str, bool]:
    """Load raw export bytes, retaining their hash and reporting tolerant parsing."""

    raw = path.read_bytes()
    raw_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    text = raw.decode("utf-8")
    used_tolerant_parser = False
    try:
        document = json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        if "control character" not in error.msg.casefold():
            raise ValueError(f"invalid HYDROS export JSON: {error.msg}") from error
        document = json.loads(text, object_pairs_hook=_unique_object, strict=False)
        used_tolerant_parser = True
    if not isinstance(document, dict):
        raise ValueError("HYDROS export root must be an object")
    unknown = set(document) - _EXPECTED_SECTIONS
    if unknown:
        raise ValueError(f"unrecognized HYDROS export sections: {', '.join(sorted(unknown))}")
    return document, raw_hash, used_tolerant_parser


def snapshot_hydros_export(path: Path, *, captured_at: datetime) -> ConfigurationSnapshot:
    """Normalize directly observed objects without inferring vendor semantics."""

    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must include a timezone")
    document, raw_hash, tolerant = load_hydros_export(path)
    option_section = document.get("Option", {})
    option_record = option_section.get("Option", {}) if isinstance(option_section, dict) else {}
    temperature_format = option_record.get("tempFmt") if isinstance(option_record, dict) else None
    entities: list[ObservedEntity] = []
    redacted_fields: list[tuple[str, str]] = []
    for section, entity_type in _ENTITY_SECTIONS.items():
        records = document.get(section, {})
        if not isinstance(records, dict):
            raise ValueError(f"HYDROS section {section} must be an object")
        for name, raw_record in records.items():
            if not isinstance(name, str) or not isinstance(raw_record, dict):
                raise ValueError(f"HYDROS section {section} contains an invalid record")
            source_path = f"$.{section}[{json.dumps(name, ensure_ascii=False)}]"
            record = _jsonable(raw_record)
            assert isinstance(record, dict)
            safe_record, record_redactions = _safe_vendor_projection(
                section,
                record,
                source_path=source_path,
            )
            redacted_fields.extend(record_redactions)
            friendly_name = safe_record.get("friendlyName")
            display_name = friendly_name if isinstance(friendly_name, str) else name
            observed_properties: dict[str, JsonValue] = {}
            if section == "System" and temperature_format == "1":
                observed_properties["temperature_display_unit"] = {
                    "value": "fahrenheit",
                    "source_path": TEMPERATURE_FORMAT_SOURCE_PATH,
                    "confidence": "operator_confirmed",
                }
            entities.append(
                ObservedEntity(
                    reefproof_id=stable_entity_id(
                        entity_type=entity_type,
                        vendor_id=_vendor_id(record),
                        source_path=source_path,
                    ),
                    vendor_id=None,
                    display_name=display_name,
                    entity_type=entity_type,
                    observed_properties=observed_properties,
                    source_path=source_path,
                    captured_at=captured_at,
                    raw_configuration_hash=raw_hash,
                    confidence=Confidence.UNKNOWN,
                    vendor_extensions=safe_record,
                )
            )
    if isinstance(option_record, dict):
        normalized_option = _jsonable(option_record)
        assert isinstance(normalized_option, dict)
        _, option_redactions = _safe_vendor_projection(
            "Option",
            normalized_option,
            source_path='$.Option["Option"]',
        )
        redacted_fields.extend(option_redactions)
    ordered = tuple(sorted(entities, key=lambda entity: entity.reefproof_id))
    ordered_redactions = sorted(redacted_fields)
    redaction_categories: dict[str, int] = {}
    for _path, category in ordered_redactions:
        redaction_categories[category] = redaction_categories.get(category, 0) + 1
    redaction_manifest: dict[str, JsonValue] = {
        "redacted_field_count": len(ordered_redactions),
        "redacted_paths": [path for path, _category in ordered_redactions],
        "categories": dict(sorted(redaction_categories.items())),
    }
    annotation_hash = content_hash({"authored_entities": [], "annotations": []})
    snapshot_content = _jsonable(
        {
            "captured_at": captured_at,
            "configuration_hash": raw_hash,
            "annotation_hash": annotation_hash,
            "entities": [entity.model_dump(mode="json") for entity in ordered],
            "authored_entities": [],
            "annotations": [],
            "vendor_extensions": {"redaction_manifest": redaction_manifest},
        }
    )
    warnings = [
        "HYDROS field semantics and relationships are unverified; "
        "imported facts remain unknown confidence.",
        "Unallowlisted HYDROS fields were omitted from normalized evidence.",
    ]
    if tolerant:
        warnings.append(
            "The original export contained an unescaped control character and "
            "required tolerant JSON parsing."
        )
    return ConfigurationSnapshot(
        provenance="OBSERVED",
        source_format="hydros_chrome_download_config",
        captured_at=captured_at,
        configuration_hash=raw_hash,
        annotation_hash=annotation_hash,
        snapshot_hash=content_hash(snapshot_content),
        entities=ordered,
        authored_entities=(),
        annotations=(),
        vendor_extensions={"redaction_manifest": redaction_manifest},
        completeness_warnings=tuple(warnings),
    )
