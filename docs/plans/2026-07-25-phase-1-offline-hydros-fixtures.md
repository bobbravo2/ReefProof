# Phase 1 Offline HYDROS Fixtures

Status: Completed.

## Outcome

Load a synthetic, repository-owned HYDROS-like configuration fixture, normalize
it into typed vendor-neutral entities and separate human annotations, and
produce deterministic snapshot evidence without network access, credentials,
private device identifiers, or mutation capability.

## Scope

In scope:

- A strict, versioned fixture envelope.
- JSON loading that rejects duplicate object keys.
- Typed observed entities with source path, capture time, confidence, raw
  configuration hash, and preserved vendor extensions.
- Separately typed human-defined entities and annotations with owner and review
  metadata.
- Stable opaque ReefProof entity and annotation IDs.
- Deterministic configuration, annotation, and snapshot hashes.
- Atomic, human-readable JSON snapshot export.
- A `reefproof snapshot --fixture ... [--output ...]` command.
- Synthetic fixtures, golden evidence, and focused tests.

Out of scope:

- Live controllers, CoralVue cloud services, authentication, HTTP, MQTT, and
  polling.
- Claims that the synthetic payload matches an observed HYDROS export.
- Reliability modeling, safety invariants, notifications, or remediation.
- Configuration writes or general-purpose transport interfaces.

## Evidence boundary

No official public configuration export or API schema was found during the
2026-07-25 research pass. The fixture is therefore labeled `AUTHORED`, not
`OBSERVED`. Its canonical mapping is an authored contract for offline product
development, not a claim about live HYDROS fields.

## Risks

- A synthetic fixture could be mistaken for a supported HYDROS schema.
- The authored canonical mapping could be mistaken for vendor-supported
  semantics.
- Future captured data could expose device identifiers or private physical
  system annotations.

These risks are controlled by explicit provenance, separate observed and
annotation layers, preserved extensions and confidence, and exclusion of
captured configuration until a sanitization policy exists.

## Evaluation

- Focused unit tests cover strict loading, stable IDs, observed/annotation
  separation, referential validation, deterministic hashing, atomic writes,
  extension preservation, CLI behavior, and golden output.
- `make check` remains the integration gate.
- All tests run without network access, credentials, or hardware.

## Completion criteria

- A repository-owned synthetic fixture loads successfully.
- Observed entities and authored annotations remain distinct.
- Stable IDs survive source reordering and vendor-identified source movement.
- Semantically identical entity ordering produces the same snapshot.
- Unknown vendor extensions survive and uncertainty is reported.
- Duplicate keys and unsupported envelope fields fail validation.
- The CLI prints or atomically writes deterministic human-readable JSON.
- Golden snapshot evidence passes.
- The implementation contains no transport, credential, or mutation surface.

## Open questions

- What official or directly observed read-only source will supply configuration?
- What sanitization policy permits captured configuration to become a fixture?
- Which live observed fields can be mapped into the authored canonical model
  without inference?
