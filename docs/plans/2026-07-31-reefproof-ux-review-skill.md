# ReefProof UX review skill

Status: Implemented; fresh-session discovery and real browser review pending.

## Outcome

Restore the bounded Workbench UX-review capability as a repository-owned Codex
skill that triggers from ordinary UX and usability-critique language.

## Scope

- Add `reefproof-ux-review` skill metadata and workflow.
- Restore only the project-local Playwright MCP registration.
- Keep one main writer and do not restore the deleted legacy UX reviewer.
- Update the harness runbook and structural regression coverage.
- Preserve exact-loopback, read-only, privacy, and no-release-approval limits.

## Acceptance

- The skill package passes the skill-creator validator.
- Metadata names the requested natural-language triggers.
- Structural tests prove skill discovery text, MCP registration, viewports,
  evidence paths, and loopback guard behavior.
- A fresh trusted Codex session exposes the skill and Playwright MCP server.
