"""Six strict, source-specific tab adapters for authored Sheet evidence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from reefproof.authored_sources.models import (
    AuthoredImportBatch,
    AuthoredSourceSnapshot,
    DiagnosticSeverity,
    ImportDiagnostic,
    NormalizedSourceRecord,
    SourceProvenance,
    SourceTabName,
    normalized_content_hash,
)


@dataclass(frozen=True)
class _TabSpec:
    identifier: str
    selected_fields: frozenset[str]
    references: tuple[tuple[str, SourceTabName, str], ...] = ()


_SPECS = {
    SourceTabName.BOM: _TabSpec(
        "BOM_ID",
        frozenset(
            {
                "BOM_ID",
                "ITEM",
                "ITEM_NAME",
                "MODEL",
                "CATEGORY",
                "RELIABILITY_TIER",
                "POWER_DOMAIN_ID",
                "DEPENDENCIES",
                "PROVIDES",
                "CRITICALITY",
                "FAILURE_IMPACT",
                "LOCATION",
                "SERIAL",
                "LOT",
                "QTY_REQUIRED",
                "LIFECYCLE",
            }
        ),
        (("POWER_DOMAIN_ID", SourceTabName.DOMAINS, "DOMAIN_ID"),),
    ),
    SourceTabName.DOMAINS: _TabSpec(
        "DOMAIN_ID",
        frozenset({"DOMAIN_ID", "NAME", "DOMAIN_TYPE", "SOURCE", "PROTECTION", "DESCRIPTION"}),
    ),
    SourceTabName.POWER: _TabSpec(
        "POWER_ID",
        frozenset(
            {
                "POWER_ID",
                "SOURCE_ID",
                "CIRCUIT_ID",
                "DOMAIN_ID",
                "DEVICE_ID",
                "POWER_DOMAIN_ID",
                "VOLTAGE",
                "CURRENT",
                "PROTECTION",
                "POWER_SUPPLY_ID",
                "NAME",
                "LOCATION",
            }
        ),
        (
            ("DOMAIN_ID", SourceTabName.DOMAINS, "DOMAIN_ID"),
            ("POWER_DOMAIN_ID", SourceTabName.DOMAINS, "DOMAIN_ID"),
            ("DEVICE_ID", SourceTabName.DEVICE_INTERFACES, "DEVICE_ID"),
        ),
    ),
    SourceTabName.DEVICE_INTERFACES: _TabSpec(
        "INTERFACE_ID",
        frozenset(
            {
                "INTERFACE_ID",
                "DEVICE_ID",
                "BOM_ID",
                "NAME",
                "INTERFACE_TYPE",
                "PORT_ID",
                "POWER_DOMAIN_ID",
                "LOCATION",
                "CABLE_ID",
                "FROM_ZONE",
                "FROM_DEVICE",
                "FROM_PORT",
                "TO_ZONE",
                "TO_DEVICE",
                "TO_PORT",
            }
        ),
        (
            ("BOM_ID", SourceTabName.BOM, "BOM_ID"),
            ("POWER_DOMAIN_ID", SourceTabName.DOMAINS, "DOMAIN_ID"),
        ),
    ),
    SourceTabName.OUTPUTS: _TabSpec(
        "OUTPUT_ID",
        frozenset(
            {"OUTPUT_ID", "DEVICE_ID", "CONTROLLER_ID", "PORT_ID", "MODE_ID", "NAME", "FUNCTION"}
        ),
        (
            ("DEVICE_ID", SourceTabName.DEVICE_INTERFACES, "DEVICE_ID"),
            ("MODE_ID", SourceTabName.MODES, "MODE_ID"),
        ),
    ),
    SourceTabName.MODES: _TabSpec(
        "MODE_ID",
        frozenset(
            {"MODE_ID", "NAME", "MEMBER_OUTPUT_IDS", "ALLOWED_BEHAVIOR", "EXCLUDED_BEHAVIOR"}
        ),
    ),
}


def _diagnostic(code: str, tab: SourceTabName, source_range: str, message: str) -> ImportDiagnostic:
    return ImportDiagnostic(
        code=code,
        severity=DiagnosticSeverity.ERROR,
        tab=tab,
        source_range=source_range,
        message=message,
    )


def normalize_source_snapshot(snapshot: AuthoredSourceSnapshot) -> AuthoredImportBatch:
    records: list[NormalizedSourceRecord] = []
    diagnostics: list[ImportDiagnostic] = []
    identifiers: dict[tuple[SourceTabName, str], set[str]] = {}
    invalid_tabs: set[SourceTabName] = set()

    for tab in snapshot.tabs:
        spec = _SPECS[tab.name]
        if not tab.rows:
            diagnostics.append(
                _diagnostic("MISSING_HEADER", tab.name, tab.source_range, "tab is empty")
            )
            invalid_tabs.add(tab.name)
            continue
        headers = tuple(value.strip() for value in tab.rows[0])
        duplicates = sorted({header for header in headers if header and headers.count(header) > 1})
        if duplicates:
            diagnostics.append(
                _diagnostic(
                    "DUPLICATE_HEADER",
                    tab.name,
                    f"{tab.name.value}!1:1",
                    f"duplicate header(s): {', '.join(duplicates)}",
                )
            )
            invalid_tabs.add(tab.name)
            continue
        if spec.identifier not in headers:
            diagnostics.append(
                _diagnostic(
                    "MISSING_HEADER",
                    tab.name,
                    f"{tab.name.value}!1:1",
                    f"required header is missing: {spec.identifier}",
                )
            )
            invalid_tabs.add(tab.name)
            continue
        selected_indexes = tuple(
            (index, header)
            for index, header in enumerate(headers)
            if header in spec.selected_fields
        )
        id_index = headers.index(spec.identifier)
        seen: set[str] = set()
        for row_number, row in enumerate(tab.rows[1:], start=2):
            padded = (*row, *("" for _ in range(max(0, len(headers) - len(row)))))
            external_id = padded[id_index].strip()
            row_range = f"{tab.name.value}!{row_number}:{row_number}"
            if not external_id:
                if any(value.strip() for value in padded):
                    diagnostics.append(
                        _diagnostic("EMPTY_ID", tab.name, row_range, f"{spec.identifier} is empty")
                    )
                continue
            if external_id in seen:
                diagnostics.append(
                    _diagnostic(
                        "DUPLICATE_EXTERNAL_ID",
                        tab.name,
                        row_range,
                        f"duplicate {spec.identifier}: {external_id}",
                    )
                )
                continue
            seen.add(external_id)
            fields = tuple((header, padded[index].strip()) for index, header in selected_indexes)
            formula_errors = tuple(value for _name, value in fields if value.startswith("#"))
            if formula_errors:
                diagnostics.append(
                    _diagnostic("FORMULA_ERROR", tab.name, row_range, formula_errors[0])
                )
                continue
            records.append(
                NormalizedSourceRecord(
                    tab=tab.name,
                    external_namespace=spec.identifier,
                    external_id=external_id,
                    fields=fields,
                    provenance=SourceProvenance(
                        tab=tab.name, row_number=row_number, source_range=row_range
                    ),
                )
            )
            for field, value in fields:
                if value:
                    identifiers.setdefault((tab.name, field), set()).add(value)
        identifiers.setdefault((tab.name, spec.identifier), set()).update(seen)

    for record in tuple(records):
        values = dict(record.fields)
        for field, target_tab, target_namespace in _SPECS[record.tab].references:
            if target_tab in invalid_tabs:
                continue
            reference = values.get(field, "")
            if reference and reference not in identifiers.get(
                (target_tab, target_namespace), set()
            ):
                diagnostics.append(
                    _diagnostic(
                        "UNRESOLVED_FOREIGN_KEY",
                        record.tab,
                        record.provenance.source_range,
                        f"{field} references unknown {target_namespace}: {reference}",
                    )
                )

    ordered_records = tuple(
        sorted(
            records, key=lambda item: (item.tab.value, item.external_id, item.provenance.row_number)
        )
    )
    digest = normalized_content_hash(ordered_records)
    batch_id = str(uuid5(NAMESPACE_URL, f"{snapshot.snapshot_hash}:{digest}:sheets-v1"))
    counts = {name: sum(record.tab is name for record in ordered_records) for name in SourceTabName}
    return AuthoredImportBatch(
        import_batch_id=batch_id,
        source_snapshot_id=snapshot.source_snapshot_id,
        source_snapshot_hash=snapshot.snapshot_hash,
        fetched_at=snapshot.fetched_at,
        normalized_content_hash=digest,
        records=ordered_records,
        record_counts=counts,
        diagnostics=tuple(diagnostics),
    )
