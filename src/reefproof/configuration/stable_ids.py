"""Deterministic, non-secret ReefProof identifiers."""

from __future__ import annotations

import hashlib

from reefproof.configuration.models import EntityType


def stable_entity_id(
    *,
    entity_type: EntityType,
    vendor_id: str | None,
    source_path: str,
) -> str:
    """Derive a stable opaque ID from the strongest available source identity."""

    identity = f"vendor:{vendor_id}" if vendor_id is not None else f"source:{source_path}"
    digest = hashlib.sha256(f"{entity_type.value}\0{identity}".encode()).hexdigest()[:16]
    return f"RP.{entity_type.value.upper()}.{digest}"


def stable_annotation_id(*, canonical_identity: bytes) -> str:
    digest = hashlib.sha256(canonical_identity).hexdigest()[:16]
    return f"RP.ANNOTATION.{digest}"
