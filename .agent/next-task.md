# Next Task

## Outcome

Implement and accept ReefProof v0.1.2 as the modular Workbench plus live Google Sheets commissioning and bulk-label vertical slice defined in:

`docs/plans/2026-08-16-v0.1.2-modular-workbench-sheets-commissioning-labels.md`

The first implementation work is Slice 0/1: reconcile dirty frontend/build ownership, capture an exact baseline from the working tree, then establish esbuild + Playwright + explicit page-owned frontend seams with deterministic fixtures for the incoming source/import/commissioning/labels APIs.

## Product gate

v0.1.2 must prove the real Primary Reef System data path:

`Google Sheets -> authored import -> human acceptance -> canonical ReefProof state -> authored/observed reconciliation -> commissioning -> deterministic label CSV`

Google Sheets is the live authored-system interface. ReefProof must not recreate generic spreadsheet editing.

Exactly these tabs are in the first import contract:

- `BOM`
- `DOMAINS`
- `POWER`
- `DEVICE_INTERFACES`
- `OUTPUTS`
- `MODES`

Stable Sheet IDs remain namespaced external identities. ReefProof owns source-independent namespace-qualified canonical identities.

## Immediate completion criteria

- Existing dirty template/build hunks have explicit ownership before modification; preserve the safe `method="post"` authentication fallback.
- Exact-pinned esbuild and Playwright Test are introduced without changing the `/assets/workbench.js` deployment contract.
- Frontend initialization uses server-authored page identity rather than selector discovery.
- Shared session/request/status seams and page-controller mount contracts exist and are browser-testable.
- The browser fixture server has future-realistic fixtures for source freshness, one authored import, invalid/ambiguous Sheet schema, commissioning state, removable cable endpoint state, and deterministic labels.
- A backend `AuthoredSystemSource` boundary and read-only live Google Sheets implementation can fetch the six in-scope tabs without directly mutating canonical state.
- Duplicate headers/IDs, broken references, and unsupported Sheet schema fail closed.
- Source snapshots/import batches retain source hash, freshness, and cell/range provenance without persisting Google credentials.
- Previously accepted/proven ReefProof state remains usable when Sheets is stale or unavailable.

## Required end-to-end acceptance before v0.1.2 release

- Sheet changes create reviewable candidates/diffs, never silent canonical mutation.
- Human acceptance produces durable canonical facts through the existing authority chain.
- Canonical `Device`, `Port`, `Cable`, and `PowerSupply` identities support stable external source bindings.
- Commissioning is derived from proof, not copied from a Sheet lifecycle cell.
- A device cannot be `COMMISSIONED` until applicable failure modes are dispositioned, electrical connections inventoried, power/comms verified, all controllable surfaces fault-tested within an accepted safe boundary, and no blocking contradiction remains.
- Canonical initial label vocabulary is exactly `DEVICE`, `PORT`, `CABLE`, `POWER SUPPLY`.
- Every removable connection uses `FROM / TO` consistently across power, control, sensor, and data cabling.
- Every removable connection generates labels at both physical ends using:

  ```text
  FROM: <zone · device · port>
  TO: <zone · device · port>
  CABLE: <stable cable display ID>
  ```

- No removable cable is commissioned until both endpoint labels are physically verified and mutually traceable to the same canonical cable and endpoint pair.
- ReefProof owns deterministic CSV export for P-touch bulk printing; it does not implement printer control or a generic label designer.
- Workbench gains task-owned Source/Imports, Commissioning, and Labels flows while Sessions stays audit/history and Database remains query-only.
- Existing Assurance, Evidence, Overview, System Map, Sessions, Database, authentication, Electron reuse, and versioned API compatibility continue to work.
- Final Python, frontend/browser, generated-contract, packaged Electron, artifact privacy, and loopback acceptance gates pass from one clean candidate.

## Boundary

No Sheet write-back, browser-held Google credentials, generic spreadsheet UI, bidirectional sync, automatic candidate acceptance, Brother printer control, live HYDROS connection, MQTT equipment behavior, controller mutation, automatic remediation, or silent inference where `UNKNOWN` is required.
