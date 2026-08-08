# ReefProof v0.1 terminology and interface contract

Status: active

## Outcome

Align the fresh-install v0.1 schema, API, CLI, Workbench, generated contracts,
Make targets, and current documentation around one versioned, resource-oriented
contract. This is a clean break: retired development routes, fields, commands,
tables, and environment variables receive no compatibility aliases or migration.
Existing database files are never deleted or silently rewritten.

## Safety and scope

HYDROS remains runtime authority. This work adds no live transport, MQTT
publication, equipment control, configuration mutation, or automatic
remediation. Unversioned HTTP paths are limited to HTML Workbench presentation,
static assets, and favicons.

## Implementation checkpoints

1. Propose an API standards ADR and add an executable resource/method inventory;
   Customer 0 acceptance remains a separate decision.
2. Rename snapshot, return-flow policy, actor provenance, bootstrap secret, CLI,
   Make, and user-visible contracts across source, fresh schema, and fixtures.
3. Consolidate system routes under `/v1/system`, expose local OpenAPI reference,
   and apply final operations methods.
4. Add request correlation, bounded structured request observations, and one
   immutable durable audit for every mutation attempt.
5. Regenerate browser contracts, update current docs, and exercise focused
   schema, API, CLI, attached-TTY, browser/API, desktop, and final repository
   gates.

## Acceptance

The route inventory, mutation metadata/audit tests, fresh-schema tests, exact CLI
matrix, generated-contract parity, `bash -n reefproof`, focused Python/Node
suites, interface acceptance, retired-term searches, and `make check` all pass
after the final change. Any unavailable private-LAN, packaged-desktop, or living
HYDROS evidence is reported as `NOT TESTED`, never inferred.
