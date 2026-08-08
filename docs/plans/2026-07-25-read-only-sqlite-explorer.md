# Read-Only SQLite Explorer

Status: Experimental implemented WIP preserved in local commits; explicitly
excluded from v0.1 release claims.

## Outcome

Provide an authenticated browser surface for inspecting ReefProof's local
SQLite schema and paginated table data, with the orientation of pgAdmin or
phpMyAdmin but none of their mutation or arbitrary-query authority.

## Product boundary

The explorer is an evidence and diagnostics surface. It is not canonical
project state and cannot establish that a fact is true merely because a row
exists.

It may:

- List allow-listed application tables and views.
- Show column types, nullability, primary keys, foreign keys, indexes, and row
  counts.
- Render fixed-order, bounded, paginated rows.
- Show the supported Alembic schema version and database integrity result.
- Copy individual displayed cell values locally.

It may not:

- Accept SQL text or expose a SQL console.
- Insert, update, delete, migrate, vacuum, attach, detach, import, or restore.
- Expose SQLite internal tables, credentials, environment values, or filesystem
  paths.
- Download the database or bypass the existing backup/restore CLI boundary.
- Change project, equipment, HYDROS, MQTT, or controller state.

## Interface

- Add a purpose-specific `/workbench/database` page labeled `Database`.
- Require the identity-bound, HTTP-only application session selected by ADR
  0004.
- Add versioned read endpoints beneath `/v1/database`:
  - `GET /schema`
  - `GET /tables/{table_name}`
- Return typed schema and page models. `table_name` must resolve through a
  server-owned allow-list; it is never interpolated from an unchecked request.
- Pagination uses bounded `limit` and non-negative `offset`. Ordering uses a
  server-derived primary-key order, falling back to a deterministic complete
  column order.
- Use repository-native TypeScript and semantic HTML tables. Do not add jQuery,
  DataTables, or another dependency unless measured dataset size later proves
  immediate value.

## Canonical-state classification

- **Canonical:** unchanged; accepted domain events remain the authority.
- **Derived diagnostics:** schema metadata, integrity status, row counts, and
  paginated row projections.
- **Presentational:** selected table, visible columns, pagination, and copied
  cell values.
- **Forbidden:** client-authored SQL and database mutation.

## Implementation slices

1. Add a query-only SQLite explorer boundary with typed schema/table-page
   models and strict identifier allow-listing.
2. Add authenticated read-only API routes and structural negative tests for
   every mutation verb and SQL-text input.
3. Add the Database page, generated TypeScript contracts, accessible data
   tables, empty/error states, and bounded pagination.
4. Run focused storage/API/browser checks, then `make check`.

## Acceptance criteria

- The schema view lists only approved ReefProof tables/views and complete
  structural metadata.
- The table view returns stable, bounded pages and preserves `NULL`, numbers,
  text, and booleans without inventing meaning.
- Missing, expired, malformed, or unauthorized sessions fail closed.
- Unknown table names and SQLite internal tables return `404`.
- POST, PUT, PATCH, and DELETE have no database-explorer capability.
- Request bodies and query parameters cannot contain SQL.
- The database connection uses read-only and query-only modes.
- The explorer works without an LLM or network access.
- Focused tests and `make check` pass on the integrated committed tree.

## Risks

- A generic table browser can be mistaken for a canonical product model; label
  it explicitly as storage diagnostics.
- Unbounded rows or large text/blob values could degrade the local interface;
  cap page size and displayed cell length.
- Identifier interpolation is unsafe even on a query-only connection; resolve
  table and ordering identifiers exclusively from inspected allow-listed
  metadata.
- Authentication work is actively changing. Do not implement against the old
  reusable session header or store browser credentials.

## Resolved questions

- Evidence document JSON and future columns are excluded from row projections
  by explicit per-table allow-lists. Complete structural metadata still exposes
  schema drift for review.
- Database remains a top-level operator diagnostics route for the first slice.
  Revisit its navigation placement only after observing actual use.
