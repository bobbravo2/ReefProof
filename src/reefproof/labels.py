"""Deterministic P-touch-compatible label manifest and CSV projection."""

from __future__ import annotations

import csv
import io
import json
import re
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field

from reefproof.authored_sources.review import ExternalIdentityBinding
from reefproof.project_state import ProjectState


def label_export_filename(project_name: str, *, version: str) -> str:
    """Return the safe, human-readable filename shared by HTTP and Workbench."""

    project_slug = re.sub(r"[^a-z0-9]+", "-", project_name.casefold()).strip("-")
    if not project_slug:
        raise ValueError("project name cannot produce an empty label-export filename")
    return f"reefproof-{project_slug}-v{version}-labels.csv"


def _canonical_id(project_id: str, kind: str, display_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", display_id.casefold()).strip("-")
    if not slug:
        raise ValueError("label display identity cannot produce an empty canonical slug")
    return f"rp:{project_id}:{kind}:{slug}"


class LabelKind(StrEnum):
    DEVICE = "DEVICE"
    PORT = "PORT"
    CABLE = "CABLE"
    POWER_SUPPLY = "POWER SUPPLY"


class LabelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    label_id: str
    label_kind: LabelKind
    canonical_subject_id: str
    display_id: str
    from_zone: str = ""
    from_device: str = ""
    from_port: str = ""
    to_zone: str = ""
    to_device: str = ""
    to_port: str = ""
    primary_text: str
    secondary_text: str = ""
    source_import_batch_ids: tuple[str, ...] = ()
    copies: int = Field(ge=1, le=100)


class LabelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    manifest_id: str
    manifest_schema_version: str = "labels-v1"
    label_policy_version: str = "labels-v1"
    project_id: str
    project_name: str
    source_project_sequence: int
    records: tuple[LabelRecord, ...]


def _facts_by_subject(state: ProjectState) -> dict[str, dict[str, str]]:
    subjects: dict[str, dict[str, str]] = {}
    for fact in state.facts:
        if isinstance(fact.value, str):
            subjects.setdefault(fact.subject_id, {})[fact.attribute] = fact.value
    return subjects


def generate_label_manifest(
    state: ProjectState,
    *,
    project_name: str,
    bindings: tuple[ExternalIdentityBinding, ...] = (),
) -> LabelManifest:
    records: dict[tuple[LabelKind, str], LabelRecord] = {}
    source_batches = {
        subject_id: tuple(
            sorted(
                {
                    binding.import_batch_id
                    for binding in bindings
                    if binding.canonical_subject_id == subject_id
                    and binding.import_batch_id is not None
                }
            )
        )
        for subject_id in {binding.canonical_subject_id for binding in bindings}
    }
    for subject_id, facts in _facts_by_subject(state).items():
        external_id = facts.get("identity.external_id", "")
        if f"rp:{state.project_id}:device:" in subject_id and external_id:
            records[(LabelKind.DEVICE, external_id)] = LabelRecord(
                label_id=f"device:{external_id}",
                label_kind=LabelKind.DEVICE,
                canonical_subject_id=subject_id,
                display_id=external_id,
                primary_text=external_id,
                secondary_text=facts.get("device.location", ""),
                source_import_batch_ids=source_batches.get(subject_id, ()),
                copies=1,
            )
        if f"rp:{state.project_id}:port:" in subject_id and external_id:
            records[(LabelKind.PORT, external_id)] = LabelRecord(
                label_id=f"port:{external_id}",
                label_kind=LabelKind.PORT,
                canonical_subject_id=subject_id,
                display_id=external_id,
                primary_text=external_id,
                secondary_text=facts.get("port.device_id", ""),
                source_import_batch_ids=source_batches.get(subject_id, ()),
                copies=1,
            )
        if f"rp:{state.project_id}:cable:" in subject_id and external_id:
            route = {
                name: facts.get(f"connection.{name}", "")
                for name in (
                    "from_zone",
                    "from_device",
                    "from_port",
                    "to_zone",
                    "to_device",
                    "to_port",
                )
            }
            if not all(route.values()):
                raise ValueError(f"cable {external_id} requires complete FROM and TO endpoints")
            records[(LabelKind.CABLE, external_id)] = LabelRecord(
                label_id=f"cable:{external_id}",
                label_kind=LabelKind.CABLE,
                canonical_subject_id=subject_id,
                display_id=external_id,
                primary_text=(
                    f"FROM: {route['from_zone']} · {route['from_device']} · {route['from_port']}"
                ),
                secondary_text=(
                    f"TO: {route['to_zone']} · {route['to_device']} · {route['to_port']} | "
                    f"CABLE: {external_id}"
                ),
                copies=2,
                source_import_batch_ids=source_batches.get(subject_id, ()),
                from_zone=route["from_zone"],
                from_device=route["from_device"],
                from_port=route["from_port"],
                to_zone=route["to_zone"],
                to_device=route["to_device"],
                to_port=route["to_port"],
            )
        if f"rp:{state.project_id}:power-supply:" in subject_id and external_id:
            records[(LabelKind.POWER_SUPPLY, external_id)] = LabelRecord(
                label_id=f"power-supply:{external_id}",
                label_kind=LabelKind.POWER_SUPPLY,
                canonical_subject_id=subject_id,
                display_id=external_id,
                primary_text=external_id,
                secondary_text=facts.get("power-supply.location", ""),
                source_import_batch_ids=source_batches.get(subject_id, ()),
                copies=1,
            )
        device_id = facts.get("interface.device_id")
        if device_id:
            canonical_device_id = _canonical_id(state.project_id, "device", device_id)
            records[(LabelKind.DEVICE, device_id)] = LabelRecord(
                label_id=f"device:{device_id}",
                label_kind=LabelKind.DEVICE,
                canonical_subject_id=canonical_device_id,
                display_id=device_id,
                primary_text=device_id,
                secondary_text=facts.get("interface.location", ""),
                source_import_batch_ids=source_batches.get(canonical_device_id, ()),
                copies=1,
            )
        port_id = facts.get("interface.port_id")
        if port_id:
            canonical_port_id = _canonical_id(state.project_id, "port", port_id)
            records[(LabelKind.PORT, port_id)] = LabelRecord(
                label_id=f"port:{port_id}",
                label_kind=LabelKind.PORT,
                canonical_subject_id=canonical_port_id,
                display_id=port_id,
                primary_text=port_id,
                secondary_text=device_id or "",
                source_import_batch_ids=source_batches.get(canonical_port_id, ()),
                copies=1,
            )
        cable_id = facts.get("interface.cable_id")
        if cable_id:
            canonical_cable_id = _canonical_id(state.project_id, "cable", cable_id)
            route = {
                name: facts.get(f"interface.{name}", "")
                for name in (
                    "from_zone",
                    "from_device",
                    "from_port",
                    "to_zone",
                    "to_device",
                    "to_port",
                )
            }
            if not all(route.values()):
                raise ValueError(f"cable {cable_id} requires complete FROM and TO endpoints")
            records[(LabelKind.CABLE, cable_id)] = LabelRecord(
                label_id=f"cable:{cable_id}",
                label_kind=LabelKind.CABLE,
                canonical_subject_id=canonical_cable_id,
                display_id=cable_id,
                primary_text=(
                    f"FROM: {route['from_zone']} · {route['from_device']} · {route['from_port']}"
                ),
                secondary_text=(
                    f"TO: {route['to_zone']} · {route['to_device']} · {route['to_port']} | "
                    f"CABLE: {cable_id}"
                ),
                copies=2,
                source_import_batch_ids=source_batches.get(canonical_cable_id, ()),
                from_zone=route["from_zone"],
                from_device=route["from_device"],
                from_port=route["from_port"],
                to_zone=route["to_zone"],
                to_device=route["to_device"],
                to_port=route["to_port"],
            )
        supply_id = facts.get("power.power_supply_id")
        if supply_id:
            canonical_supply_id = _canonical_id(state.project_id, "power-supply", supply_id)
            records[(LabelKind.POWER_SUPPLY, supply_id)] = LabelRecord(
                label_id=f"power-supply:{supply_id}",
                label_kind=LabelKind.POWER_SUPPLY,
                canonical_subject_id=canonical_supply_id,
                display_id=supply_id,
                primary_text=supply_id,
                secondary_text=facts.get("power.location", ""),
                source_import_batch_ids=source_batches.get(canonical_supply_id, ()),
                copies=1,
            )
    ordered = tuple(
        records[key] for key in sorted(records, key=lambda item: (item[0].value, item[1]))
    )
    payload = [record.model_dump(mode="json") for record in ordered]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return LabelManifest(
        manifest_id=f"label-manifest-{digest}",
        project_id=state.project_id,
        project_name=project_name,
        source_project_sequence=state.last_sequence,
        records=ordered,
    )


_CSV_FIELDS = (
    "label_kind",
    "display_id",
    "from_zone",
    "from_device",
    "from_port",
    "to_zone",
    "to_device",
    "to_port",
    "primary_text",
    "secondary_text",
    "copies",
)


def render_label_csv(manifest: LabelManifest) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in manifest.records:
        document = record.model_dump(mode="json")
        writer.writerow({field: document[field] for field in _CSV_FIELDS})
    return output.getvalue()
