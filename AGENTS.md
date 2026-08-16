# ReefProof Agent Guide

Use this file as the short operating contract. Detailed contributor, reviewer, and operational procedures live in the linked repository documents.

## Permanent safety boundary

HYDROS remains runtime authority.

> ReefProof may observe, model, challenge, and alert on a living system. It may not silently take control of one.

Never mutate HYDROS configuration or equipment, change outputs, modes, schedules, or firmware, publish MQTT messages, expose general-purpose control APIs, or perform automatic remediation.

Treat every live transport as write-capable until structural evidence proves otherwise. Use offline fixtures, never a living system as an informal test fixture. Never commit credentials, device identifiers, private physical annotations, captured private configuration, local databases, or browser evidence.

## Authority

Resolve conflicts in this order:

1. Permanent safety boundary.
2. Current explicit human instruction.
3. Accepted ADRs.
4. Executable behavior and tests.
5. `AGENTS.md`.
6. Active task or plan.
7. Status and other documentation.
8. Agent inference.

Repository state outranks conversation summaries. Do not silently resolve a material conflict; report it and request the one decision needed to proceed.

## Start and task routing

Before implementation, run:

`python .codex/skills/reefproof-project-grounding/scripts/extract.py --repo . --format llm`

- Need architecture or capability inventories? Rerun with `--detail`.
- Need machine-readable fields? Use `--format json`; do not use JSON as the default LLM context.

Then inspect only task-relevant files and their Git state. Choose one route:

- **Read-only review:** inspect and report; do not edit, commit, publish, or
  perform external writes.
- **Small compatible repair:** preserve existing interfaces and safety policy;
  no dated plan or reviewer is required. Add focused regression coverage and
  exercise the exact affected interface.
- **Material change:** create a dated plan for safety or architecture changes,
  dependencies, protocols, new or breaking public interfaces, or work expected
  to span sessions. Use the optional read-only reviewer only at a material
  checkpoint, then run the final repository gate and request human acceptance.

Do not add dependencies, live network behavior, credentials, or future-phase abstractions without explicit scope and immediate value.

## Minimal implementation policy

- Keep ReefProof as the smallest possible slice of domain logic that helps new saltwater reef keepers succeed. Before writing custom infrastructure, reuse repository, standard-library, framework, and established-module capabilities. Otherwise prefer a mature, maintained, compatibly licensed component, subject to the dependency rule above.
- Custom code must express a ReefProof-specific beginner outcome, safety rule, evidence model, or integration seam unavailable elsewhere. Do not recreate generic framework features, utilities, protocols, persistence, validation, authentication, UI primitives, or build tooling. Prefer adapters and configuration; delete or consolidate redundancy when a smaller supported path preserves behavior and safety.
- In proposals and reviews, identify the domain logic retained, capability reused, and need for each new abstraction or dependency. Treat avoidable custom code and framework duplication as defects.
- For common SDLC operations, use repository-root `make help` and its domain targets, not their internals.
- Use the repository-owned local-CI skill (`$reefproof-local-ci`) for workflow emulation and artifact gates, and `.agent/evals.yaml` for registered focused evaluations.
- Do not copy low-level commands from historical plans; they are non-authoritative evidence.

## Dirty-tree handling

Never discard, reset, stash, stage, or commit unexplained existing work. If a
task-relevant file is dirty, inspect its diff. Preserve non-overlapping work and
edit only the assigned hunks. If ownership or hunk overlap remains unclear,
stop before editing that file and request one concrete handoff decision.

The main Codex session is the only writer. The optional `reefproof_reviewer` is
read-only and advisory; its complete contract is in
`docs/player-coach-loop.md`.

## Validation and evidence

Do not report a user-visible defect as fixed until the exact launcher, endpoint,
or interface reported by the user passes a current acceptance test:

- CLI or REPL: exercise the affected path through attached-TTY `./reefproof`.
- API or browser: start the service and inspect the affected endpoint or browser
  flow; a health response alone is insufficient.
- Shell launcher: run `bash -n` on the shell file.
- Internal Python behavior: run focused automated tests.

For a small compatible repair, focused tests plus the exact interface
acceptance are the final gate. For a material change, also run the applicable
deterministic repository gate from `.agent/evals.yaml` or the repository-owned
local-CI skill.

Do not weaken an accurate failing test. Fix behavior or report the failure and
its consequence. Unit tests support interface evidence; they do not replace it.

Use `VERIFIED`, `OBSERVED`, `INFERRED`, `ASSUMED`, `UNKNOWN`, and `NOT TESTED`
when they clarify evidence. `UNKNOWN` is not `PASS`. Distinguish authored
requirements from observed device behavior. For each reported evaluation,
include the command, result, and exercised boundary.

## Changes and closeout

Keep each change to one observable outcome with focused tests and directly
affected documentation. Stage explicit paths or hunks only. Before a requested
commit, review the staged paths and run `git diff --cached --check`. Pushes,
tags, publication, deployment, and live HYDROS access require separate authority.

Keep generated artifacts with their source. For Workbench source and generated
asset commands, follow `CONTRIBUTING.md`; do not edit generated JavaScript. For release, tag, GHCR, or release-notes work, follow `docs/releasing.md`.

Update `.agent/current-state.md` and `.agent/next-task.md` only when the project
capability, current gate, or assigned next task changes. At handoff report what
changed, evaluations and results, what was not tested, residual risks, and the
exact next task when it changed.
