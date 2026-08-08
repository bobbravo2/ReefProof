# Phase 0 Product Shell

Status: Completed on 2026-07-25.

## Outcome

Deliver a runnable, local-only ReefProof shell with onboarding, health checks,
reproducible quality gates, and a lightweight agent-usage ledger.

## Scope and non-goals

In scope:

- Python 3.13 packaging and the `reefproof` CLI.
- Typed settings, focused logging, and doctor checks.
- Local quality tooling and CI.
- Append-only agent-usage recording, validation, and aggregation.
- Repository-local Stop and SessionEnd hook collection with idempotent repair.
- Tests and documentation for the Phase 0 acceptance criteria.

Non-goals:

- HYDROS connectivity, authentication, HTTP, MQTT, or polling.
- Configuration models, normalization, reliability graphs, or invariants.
- Mutation, remediation, Home Assistant, persistence databases, or dashboards.
- Remote usage or cost collection and estimated dollar cost.

## Dependency value

- Typer provides the immediately required contributor-facing CLI.
- Pydantic v2 provides typed settings validation without an additional settings
  dependency.
- structlog provides stable named events and selectable human/JSON rendering.
- Pytest provides the required deterministic test suite.
- Ruff provides formatting and linting.
- Pyright provides static type checking.

## Risks

- The active harness may not expose token telemetry; unavailable values must
  remain `null` and display as `UNKNOWN`.
- Codex JSONL evolves; its adapter must be narrow, version-aware, fixture-tested,
  and fail safely.
- Hook transcript format is explicitly unstable; only recognized usage fields
  may be retained, and missing fields must remain unknown.
- Bootstrap requires `uv` and package downloads on a clean machine, while all
  ReefProof runtime commands must remain network-free.
- Doctor checks must distinguish repository development health from an installed
  CLI running outside a checkout.

## Evaluation

- Target individual unit-test modules after each coherent slice.
- Run `make check` only at meaningful integration points.
- Run the exact acceptance command sequence near completion.
- Audit source and tests for network and product-domain behavior.

## Completion criteria

- All requested CLI and Make targets work.
- Tests cover the requested Phase 0 behaviors.
- Usage records are validated, append-only after completion, and honest about
  unknown values and cost.
- Documentation and agent handoff files accurately identify Phase 1.
- No HYDROS transport or product-domain implementation exists.

## Open questions

- How can an active interactive Codex harness export authoritative per-session
  usage without private-file or terminal scraping?
- When will hook transcripts expose a stable, versioned usage schema?
