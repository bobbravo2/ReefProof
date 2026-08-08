# v0.1 Database Release Contract

## Outcome

Establish one fresh-install SQLite schema as the v0.1 release contract so an
offline HYDROS export can be normalized, persisted, reopened, inspected, and
backed up without redundant session documents or ambiguous migration history.

## Accepted compatibility boundary

- v0.1 supports databases created from the release schema baseline.
- Databases created by unreleased development migrations `0001` through `0008`
  are disposable and are not upgraded.
- Operators prepare for v0.1 by exporting source evidence and creating a fresh
  database; ReefProof must never rewrite or silently adopt an incompatible file.
- This reset does not authorize deletion of an operator database. Runtime code
  continues to fail closed on an unsupported schema.

## Schema contract

- One Alembic baseline creates the complete v0.1 schema.
- Query columns remain authoritative for identity, joins, bounded projections,
  and retained summaries.
- Typed JSON documents remain only where they preserve canonical evidence or an
  immutable domain/audit record; SQLite requires each stored document to be
  valid JSON.
- `operator_sessions` uses its typed columns only. It does not duplicate the
  complete row in `document_json`.
- Evaluation summaries, active-finding projections, transition evidence, and
  historical rule previews remain intentionally denormalized because their
  detail may be pruned or their original calculation must remain replayable.
- Foreign keys, bounded enums, non-negative counters, and immutable-stream
  triggers enforce the parts of the contract SQLite can prove directly.

## Acceptance

1. A new database migrates directly to the single v0.1 revision and enables WAL.
2. The schema inventory matches the release contract and contains no redundant
   `operator_sessions.document_json` column.
3. Invalid JSON and inconsistent evaluation summary counts are rejected by
   SQLite constraints.
4. Operator sessions persist, enumerate, authenticate, and revoke once using
   typed columns only.
5. A sanitized offline HYDROS export persists one typed normalized snapshot and
   evaluation; reopen/model validation, foreign-key checks, and
   `PRAGMA integrity_check` pass.
6. Storage backup and restore accept only the v0.1 schema revision and verify
   the same evidence projection after transfer.
7. The canonical local quality gate passes without modifying unrelated WIP.

## Exclusions

No live HYDROS access, MQTT publication, controller mutation, automatic
remediation, general SQL API, old-development-database conversion, release
publication, deployment, or deletion of an existing database.
