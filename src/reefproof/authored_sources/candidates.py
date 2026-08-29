"""Deterministic candidates derived from valid authored imports."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from reefproof.authored_sources.models import (
    AuthoredImportBatch,
    NormalizedSourceRecord,
    SourceTabName,
)
from reefproof.project_state import CandidateFact

_KINDS = {
    SourceTabName.BOM: "bom-item",
    SourceTabName.DOMAINS: "power-domain",
    SourceTabName.POWER: "power",
    SourceTabName.DEVICE_INTERFACES: "interface",
    SourceTabName.OUTPUTS: "output",
    SourceTabName.MODES: "mode",
}
_SUPPORTED_NAMESPACES = {
    "identity",
    *_KINDS.values(),
    "device",
    "port",
    "connection",
    "power-supply",
}
_ALLOWED_ATTRIBUTES = {
    "identity.external_id",
    "identity.external_namespace",
    *(
        f"bom-item.{name}"
        for name in {
            "bom_id",
            "item",
            "item_name",
            "model",
            "category",
            "reliability_tier",
            "power_domain_id",
            "dependencies",
            "provides",
            "criticality",
            "failure_impact",
            "location",
            "serial",
            "lot",
            "qty_required",
            "lifecycle",
        }
    ),
    *(
        f"power-domain.{name}"
        for name in {
            "domain_id",
            "name",
            "domain_type",
            "source",
            "protection",
            "description",
        }
    ),
    *(
        f"power.{name}"
        for name in {
            "power_id",
            "source_id",
            "circuit_id",
            "domain_id",
            "device_id",
            "power_domain_id",
            "voltage",
            "current",
            "protection",
            "power_supply_id",
            "name",
            "location",
        }
    ),
    *(
        f"interface.{name}"
        for name in {
            "interface_id",
            "device_id",
            "bom_id",
            "name",
            "interface_type",
            "port_id",
            "power_domain_id",
            "location",
            "cable_id",
            "from_zone",
            "from_device",
            "from_port",
            "to_zone",
            "to_device",
            "to_port",
        }
    ),
    *(
        f"output.{name}"
        for name in {
            "output_id",
            "device_id",
            "controller_id",
            "port_id",
            "mode_id",
            "name",
            "function",
        }
    ),
    *(
        f"mode.{name}"
        for name in {
            "mode_id",
            "name",
            "member_output_ids",
            "allowed_behavior",
            "excluded_behavior",
        }
    ),
    "device.location",
    "device.bom_id",
    "device.item_name",
    "device.power_domain_id",
    "port.device_id",
    "connection.cable_id",
    "connection.device_id",
    "connection.from_zone",
    "connection.from_device",
    "connection.from_port",
    "connection.to_zone",
    "connection.to_device",
    "connection.to_port",
    "power-supply.location",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError("external identity cannot produce an empty canonical slug")
    return slug


def canonical_subject_id(project_id: str, record: NormalizedSourceRecord) -> str:
    return f"rp:{project_id}:{_KINDS[record.tab]}:{_slug(record.external_id)}"


def record_candidate_values(record: NormalizedSourceRecord) -> tuple[tuple[str, str], ...]:
    """Return the complete deterministic fact set for one normalized source object."""

    return (
        ("identity.external_id", record.external_id),
        ("identity.external_namespace", record.external_namespace),
        *(
            (f"{_KINDS[record.tab]}.{name.casefold()}", value)
            for name, value in record.fields
            if value
        ),
    )


def import_candidates(
    batch: AuthoredImportBatch,
    *,
    project_id: str,
    proposed_by_actor_id: str,
    proposed_at: datetime,
) -> tuple[CandidateFact, ...]:
    if not batch.valid:
        raise ValueError("invalid authored import cannot create canonical candidates")
    candidates: list[CandidateFact] = []
    canonical_sources: dict[str, tuple[str, str]] = {}
    evidence_id = f"evidence-source-{batch.source_snapshot_id.casefold()}"
    proposed_facts: list[tuple[str, str, str]] = []
    bom_fields = {
        record.external_id: dict(record.fields)
        for record in batch.records
        if record.tab is SourceTabName.BOM
    }
    for record in batch.records:
        subject_id = canonical_subject_id(project_id, record)
        source_identity = (record.external_namespace, record.external_id)
        previous_source = canonical_sources.setdefault(subject_id, source_identity)
        if previous_source != source_identity:
            raise ValueError("distinct external identities collide in the canonical namespace")
        proposed_facts.extend(
            (subject_id, attribute, value) for attribute, value in record_candidate_values(record)
        )
        fields = dict(record.fields)
        if record.tab is SourceTabName.DEVICE_INTERFACES:
            device_id = fields.get("DEVICE_ID", "")
            port_id = fields.get("PORT_ID", "")
            cable_id = fields.get("CABLE_ID", "")
            if device_id:
                device_subject = f"rp:{project_id}:device:{_slug(device_id)}"
                bom_id = fields.get("BOM_ID", "")
                proposed_facts.extend(
                    (
                        (device_subject, "identity.external_id", device_id),
                        (device_subject, "identity.external_namespace", "DEVICE_ID"),
                        (device_subject, "device.location", fields.get("LOCATION", "")),
                        (device_subject, "device.bom_id", bom_id),
                        (
                            device_subject,
                            "device.item_name",
                            bom_fields.get(bom_id, {}).get("ITEM_NAME", ""),
                        ),
                        (
                            device_subject,
                            "device.power_domain_id",
                            fields.get("POWER_DOMAIN_ID", ""),
                        ),
                    )
                )
            if port_id:
                port_subject = f"rp:{project_id}:port:{_slug(port_id)}"
                proposed_facts.extend(
                    (
                        (port_subject, "identity.external_id", port_id),
                        (port_subject, "identity.external_namespace", "PORT_ID"),
                        (port_subject, "port.device_id", device_id),
                    )
                )
            if cable_id:
                cable_subject = f"rp:{project_id}:cable:{_slug(cable_id)}"
                proposed_facts.extend(
                    (
                        (cable_subject, "identity.external_id", cable_id),
                        (cable_subject, "identity.external_namespace", "CABLE_ID"),
                        (cable_subject, "connection.cable_id", cable_id),
                        (cable_subject, "connection.device_id", device_id),
                        *(
                            (
                                cable_subject,
                                f"connection.{name.casefold()}",
                                fields.get(name, ""),
                            )
                            for name in (
                                "FROM_ZONE",
                                "FROM_DEVICE",
                                "FROM_PORT",
                                "TO_ZONE",
                                "TO_DEVICE",
                                "TO_PORT",
                            )
                        ),
                    )
                )
        if record.tab is SourceTabName.POWER:
            supply_id = fields.get("POWER_SUPPLY_ID", "")
            if supply_id:
                supply_subject = f"rp:{project_id}:power-supply:{_slug(supply_id)}"
                proposed_facts.extend(
                    (
                        (supply_subject, "identity.external_id", supply_id),
                        (supply_subject, "identity.external_namespace", "POWER_SUPPLY_ID"),
                        (supply_subject, "power-supply.location", fields.get("LOCATION", "")),
                    )
                )
    seen: set[tuple[str, str, str]] = set()
    for subject_id, attribute, value in proposed_facts:
        if not value or (subject_id, attribute, value) in seen:
            continue
        seen.add((subject_id, attribute, value))
        if attribute == "identity.external_id":
            previous_source = canonical_sources.setdefault(subject_id, ("derived", value))
            if previous_source[1] != value:
                raise ValueError("distinct external identities collide in the canonical namespace")
        identity = uuid5(
            NAMESPACE_URL,
            f"{batch.import_batch_id}:{subject_id}:{attribute}:{value}",
        ).hex
        candidates.append(
            CandidateFact(
                candidate_fact_id=f"candidate-import-{identity}",
                project_id=project_id,
                subject_id=subject_id,
                attribute=attribute,
                proposed_value=value,
                proposed_by_actor_id=proposed_by_actor_id,
                proposed_at=proposed_at,
                evidence_ids=(evidence_id,),
            )
        )
    return tuple(candidates)


def validate_import_candidate_fact(candidate: CandidateFact) -> None:
    prefix = f"rp:{candidate.project_id}:"
    if not candidate.subject_id.startswith(prefix):
        raise ValueError("imported candidate subject must use the project canonical namespace")
    namespace = candidate.attribute.split(".", 1)[0]
    if namespace not in _SUPPORTED_NAMESPACES:
        raise ValueError("unsupported imported candidate namespace")
    if candidate.attribute not in _ALLOWED_ATTRIBUTES:
        raise ValueError("unsupported imported candidate attribute")
    subject_kind = candidate.subject_id.removeprefix(prefix).split(":", 1)[0]
    expected_kind = "cable" if namespace == "connection" else namespace
    if namespace != "identity" and subject_kind != expected_kind:
        raise ValueError("imported candidate attribute does not match its canonical subject kind")
    if not isinstance(candidate.proposed_value, str) or not candidate.proposed_value.strip():
        raise ValueError("imported candidate values must be non-empty strings")
    if not candidate.evidence_ids or not all(
        evidence.startswith("evidence-source-") for evidence in candidate.evidence_ids
    ):
        raise ValueError("imported candidates require source snapshot evidence")
