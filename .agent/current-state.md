# Current State

Last updated: 2026-08-28

## Current gate

ReefProof v0.1.1 is the current released baseline. The next product gate is v0.1.2: a modular Workbench plus one complete live Google Sheets commissioning and bulk-label vertical slice for the Primary Reef System.

The accepted v0.1.2 plan is:

`docs/plans/2026-08-16-v0.1.2-modular-workbench-sheets-commissioning-labels.md`

The gate is no longer satisfied by frontend modularization alone. v0.1.2 must prove:

`Google Sheets -> authored import -> human acceptance -> canonical ReefProof state -> authored/observed reconciliation -> commissioning -> deterministic label CSV`

HYDROS remains runtime authority. ReefProof remains structurally read-only toward HYDROS and Google Sheets.

## Released baseline

- v0.1.1 was published on 2026-08-15 as the supported hotfix for the v0.1.0 Workbench bundle omission.
- The v0.1.1 OCI release restores the browser Workbench bundle and preserves the existing database schema.
- The released package version is `0.1.1`; the dirty working candidate reports `0.1.2`.
- Existing local-managed and remote-hosted desktop/runtime boundaries, versioned APIs, authentication/session behavior, SQLite backup/replay behavior, and no-control HYDROS boundary remain compatibility requirements for v0.1.2.

## Current capability

- Offline HYDROS fixtures and operator-supplied exports normalize into deterministic evidence.
- Typed reliability graphs and fifteen invariants preserve `PASS`, `FAIL`, and `UNKNOWN` with explanations and provenance.
- SQLite stores configuration snapshots, evaluation runs/results, finding transitions, return-flow policy revisions, authority chains, trust events, and schema migrations.
- The local CLI, loopback Workbench, OCI image, and macOS Electron shell exist without live HYDROS access, MQTT publication, controller mutation, or automatic remediation.
- All non-presentation APIs are versioned under `/v1` and generated OpenAPI contracts feed the TypeScript frontend.
- All nine Workbench routes render page-owned templates and mount page controllers through server-authored page identity while retaining one tracked generated `/assets/workbench.js`. Shared code owns the session shell, request boundary, reconciliation component, and registry; selector-discovered initialization and obsolete route implementations have been removed from the entrypoint.
- Exact-pinned Playwright Test and Chromium run authenticated real `/workbench*` routes against an isolated loopback ReefProof fixture service, execute the tracked generated asset, reject off-origin traffic, and cover Overview, Source, Commissioning, Labels, Assurance, Evidence, System Map, Sessions, and Database.
- The v0.1.2 backend has a server-only read-only Google Sheets credential/source boundary, strict six-tab normalization, append-only source/fetch/import evidence, deterministic semantic diffs and candidates, durable external identity bindings, and fresh-TOTP batch acceptance/rejection. Equivalent content refreshes freshness without duplicating canonical facts; failed fetches preserve accepted state and report `UNAVAILABLE`.
- Authenticated Source/Imports, Commissioning, and Labels Workbench routes now use generated contracts and the tracked bundle. They can fetch/review an authored batch, derive evidence-backed device commissioning posture, record bounded verification/failure-mode/physical-label evidence, and download a deterministic versioned project-named CSV.
- Canonical imported Device, Port, Cable, and PowerSupply subjects are separate from Sheet row identity. Commissioning remains UNKNOWN/BLOCKED until identity/location, electrical and endpoint inventory, DEVICE/PORT/both cable-end labels, power/comms evidence, every authored control-surface fault test, applicable failure-mode dispositions, and contradiction checks pass.
- The complete fixture-backed source sync -> grouped review -> acceptance -> explicit authored/observed identity binding -> commissioning state machine -> four-kind CSV path passes in real Chromium in 23.1 seconds. It verifies physical connection, power, communications disposition, bounded fault test, all failure modes, DEVICE/PORT/CABLE labels, final `COMMISSIONED`, and the versioned project-named CSV. This is local fixture-backed evidence, not live Google Sheets acceptance.
- Explicit HYDROS identity bindings require accepted canonical identity, OBSERVED evidence, fresh authority/TOTP, rationale, and an evidence reference. Reconciliation never guesses by display name or topology, and conflicts block commissioning. HYDROS remains offline, sanitized, read-only evidence.
- Database schema 0006 preserves append-only Sheet and non-Sheet identity provenance; downgrade refuses to discard immutable non-Sheet evidence. Label source provenance excludes non-Sheet evidence from import-batch identifiers.
- The final dirty-tree source gate passes after reviewer acceptance: `make check` verifies formatting/lint/type checking, generated OpenAPI/TypeScript and Workbench parity, nine Node tests, five loopback Chromium flows, 25 desktop source tests, and 561 Python tests. The clean candidate artifact gate remains unproven because repository packaging correctly refuses the uncommitted dirty tree.
- Canonical project acceptance currently supports append-only candidate -> human decision -> domain event replay, but candidate domain validation is still narrow and must be extended for authored system imports.
- The legacy fixed Mock Collective return-flow API remains compatible for Assurance/Evidence fixtures, but the real Overview and System Map no longer present it as the Primary Reef System model.

## Accepted v0.1.2 product decisions

- Google Sheets is the live authored-system interface; ReefProof must not recreate a generic spreadsheet UI.
- Exactly these tabs are in the first live import contract: `BOM`, `DOMAINS`, `POWER`, `DEVICE_INTERFACES`, `OUTPUTS`, `MODES`.
- Trust flows from Sheet source evidence into ReefProof only through explicit review and human acceptance; sync never silently overwrites canonical state.
- Previously accepted/proven ReefProof life-support state remains usable when the Sheet is stale, unavailable, or later changed.
- Stable Sheet identifiers remain namespaced external identities; ReefProof owns source-independent namespace-qualified canonical identities.
- Commissioning is evidence-backed and ReefProof-owned. A Sheet lifecycle cell is an authored claim, not commissioning authority.
- A commissioned device has inventoried identity and electrical connections, dispositioned failure modes, complete labels, verified power/comms where applicable, and accepted fault-test evidence for every applicable controllable surface.
- Canonical initial label vocabulary is `DEVICE`, `PORT`, `CABLE`, `POWER SUPPLY`.
- Every removable connection is labeled at both ends using `FROM / TO / CABLE`, consistently across power, control, sensor, and data cabling.
- Endpoint completeness is a commissioning invariant: no removable cable is commissioned until both labels are physically verified and mutually traceable.
- ReefProof owns deterministic CSV export for Brother P-touch bulk printing; direct printer control and generic label design are out of scope.

## Known source-schema issue to handle explicitly

The current production workbook contains duplicated `POWER_DOMAIN_ID` headers in `DEVICE_INTERFACES`. The v0.1.2 Sheet adapter must report this as an explicit schema diagnostic unless an accepted source mapping disambiguates it. Silent first-column/last-column selection is forbidden.

## Immediate implementation focus

- Create an authorized clean candidate identity for the reviewed v0.1.2 tree, then run candidate migration, packaged Electron, OCI, artifact-privacy, and loopback packaging acceptance without publishing or deploying. Live production Google Sheets and P-touch acceptance require explicit external-system authority and remain outside fixture evidence.

## Blocking unknowns / implementation decisions intentionally deferred behind replaceable seams

- Exact Google credential mechanism for local-managed versus remote-hosted deployment. It must remain server-side, read-only, replaceable, and absent from evidence/backups/browser state.
- The final canonical instance slugs for all physical devices/ports/cables. The canonical ID grammar is accepted; individual instance creation remains explicit rather than inferred from BOM quantity.
- Exact safe fault-injection procedure per control surface. v0.1.2 must model required evidence without forcing unsafe destructive tests.
- Exact P-touch column/template mapping after validating the deterministic ReefProof CSV against the current Brother bulk-print workflow.

## History

v0.1.0 was the first public release but omitted the Workbench JavaScript bundle in the published container. v0.1.1 superseded it and is the supported released baseline. Dated plans, ADRs, release notes, and Git history remain authoritative for completed work; this file contains only context needed for the current gate and agent handoff.
