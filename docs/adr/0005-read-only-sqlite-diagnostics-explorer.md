# ADR 0005: Read-Only SQLite Diagnostics Explorer

- Status: Experimental preserved WIP, outside v0.1 release scope
- Date: 2026-07-25

## Context

ReefProof needs a durable way to inspect its local SQLite schema and storage
records during commissioning and development. Familiar database tools such as
pgAdmin and phpMyAdmin provide useful orientation, but their SQL consoles,
mutation controls, imports, exports, and administrative authority violate the
ReefProof v0.1 read-only safety boundary.

SQLite rows are persistence evidence. They are not automatically canonical
project facts: accepted domain events and deterministic replay remain the
authority for project state.

## Decision

ReefProof provides a purpose-built local Database page at
`/workbench/database` and versioned read endpoints beneath `/v1/database`.

The explorer:

- requires the same signed, expiring, identity-bound browser session as other
  protected local workbench operations;
- opens SQLite with `mode=ro` and enables `PRAGMA query_only`;
- exposes complete structural metadata only for a server-owned table
  allow-list;
- exposes row data through a separate per-table column allow-list;
- orders rows deterministically and limits pages to at most 100 rows;
- represents `NULL`, numeric, text, and blob cells explicitly;
- truncates long text and represents blobs only by byte count;
- uses native TypeScript and semantic HTML tables with no new dependency.

The explorer does not accept SQL, request bodies, database paths, or arbitrary
identifiers. It has no write verbs, migration action, import/export action,
database download, or device/controller capability. Document payloads and
future schema columns fail closed from row projections until explicitly
reviewed and allow-listed.

## Canonical-state impact

None. Schema metadata, integrity results, row counts, and row projections are
derived diagnostics. Selected tables and pages are presentational browser
state. The explorer cannot accept candidate facts, produce domain events, or
change canonical state.

Committing this implementation on the preservation branch does not promote it
into current v0.1 capability or release evidence.

## LLM dependency

None. SQLite inspection, response validation, pagination, and rendering are
deterministic and work without a model or network connection.

## Consequences

- Operators gain a familiar schema-and-table inspection surface without
  acquiring general database administration authority.
- Adding a table or exposed column requires an explicit code and test change.
- Full structural schema metadata may reveal column names that are deliberately
  absent from row projections; this makes exclusion and schema drift visible
  without exposing the values.
- Database repair, backup, restore, migration, and raw SQL remain CLI or
  operator workflows outside this browser surface.
- Authentication is local authorization, not evidence that a displayed row is
  true or safe.

## Rejected alternatives

- Embedding pgAdmin, phpMyAdmin, SQLite Web, or a general grid dependency:
  rejected because they add unnecessary dependencies and commonly expose
  mutation or arbitrary-query capability.
- A browser SQL console restricted to `SELECT`: rejected because parsing and
  enforcing safe SQLite statements is unnecessary risk for the current need.
- Returning `SELECT *` for allow-listed tables: rejected because present and
  future sensitive payload columns would become visible implicitly.
