# Current State

Last updated: 2026-08-16

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
- The current package version is `0.1.1`.
- Existing local-managed and remote-hosted desktop/runtime boundaries, versioned APIs, authentication/session behavior, SQLite backup/replay behavior, and no-control HYDROS boundary remain compatibility requirements for v0.1.2.

## Current capability

- Offline HYDROS fixtures and operator-supplied exports normalize into deterministic evidence.
- Typed reliability graphs and fifteen invariants preserve `PASS`, `FAIL`, and `UNKNOWN` with explanations and provenance.
- SQLite stores configuration snapshots, evaluation runs/results, finding transitions, return-flow policy revisions, authority chains, trust events, and schema migrations.
- The local CLI, loopback Workbench, OCI image, and macOS Electron shell exist without live HYDROS access, MQTT publication, controller mutation, or automatic remediation.
- All non-presentation APIs are versioned under `/v1` and generated OpenAPI contracts feed the TypeScript frontend.
- The current Workbench remains structurally monolithic: one conditional Jinja template plus one large TypeScript controller initialize Overview, Assurance, Evidence, System Map, Sessions, Database, session/auth, trust, electrical posture, and project surfaces.
- The current real-system electrical posture can expose imported HYDROS evidence and unproven authored domains, but the Workbench does not yet provide live Google Sheets authored import, electrical mapping authoring/review, commissioning workflow, or label generation.
- Canonical project acceptance currently supports append-only candidate -> human decision -> domain event replay, but candidate domain validation is still narrow and must be extended for authored system imports.
- The current physical proposal model is still the fixed Mock Collective return-flow model and must not become the permanent canonical physical-system model.

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

- Reconcile ownership of current dirty frontend/build hunks and capture a fresh exact test baseline.
- Add exact-pinned esbuild and Playwright Test while preserving the single `/assets/workbench.js` artifact.
- Replace selector-discovered frontend initialization with explicit server-authored page mounts and narrow shared seams.
- Add deterministic browser fixtures for source/import/commissioning/labels before those pages are implemented.
- Add the backend `AuthoredSystemSource` provider boundary and a read-only server-side Google Sheets source implementation.
- Build strict six-tab normalization, source provenance, source freshness, import-batch persistence, semantic diffs, identity bindings, and deterministic candidate validation.

## Blocking unknowns / implementation decisions intentionally deferred behind replaceable seams

- Exact Google credential mechanism for local-managed versus remote-hosted deployment. It must remain server-side, read-only, replaceable, and absent from evidence/backups/browser state.
- The final canonical instance slugs for all physical devices/ports/cables. The canonical ID grammar is accepted; individual instance creation remains explicit rather than inferred from BOM quantity.
- Exact safe fault-injection procedure per control surface. v0.1.2 must model required evidence without forcing unsafe destructive tests.
- Exact P-touch column/template mapping after validating the deterministic ReefProof CSV against the current Brother bulk-print workflow.

## History

v0.1.0 was the first public release but omitted the Workbench JavaScript bundle in the published container. v0.1.1 superseded it and is the supported released baseline. Dated plans, ADRs, release notes, and Git history remain authoritative for completed work; this file contains only context needed for the current gate and agent handoff.
