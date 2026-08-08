---
name: reefproof-ux-review
description: Perform a bounded, read-only usability and accessibility critique of the local ReefProof Workbench with loopback-only Playwright MCP evidence. Use when the user asks for a "UX review", "UX critique", "usability review", "usability critique", "help with a usability critique", visual review, accessibility review, responsive-layout review, or release-candidate Workbench screenshots.
---

# ReefProof UX Review

Read `docs/ux-review-harness.md` completely before starting. Treat its origin,
viewport, evidence, privacy, and reporting rules as mandatory.

## Workflow

1. Run ReefProof project grounding and inspect `git status --short`.
2. Confirm the review target is the local Mock Collective Workbench at the
   exact allowed origin `http://127.0.0.1:8787`.
3. Check both `/v1/system/health/live` and `/workbench`; health alone is insufficient.
   Start the service only when the user requested an active review and no
   suitable loopback instance exists.
4. Use only the `reefproof_playwright` MCP server. If it is unavailable, report
   the missing prerequisite and ask the user to restart Codex from the trusted
   repository after completing the runbook setup. Do not substitute an
   unrestricted browser.
5. Perform one bounded pass at the runbook's desktop and narrow-mobile
   viewports. Inspect visual hierarchy, responsive behavior, accessibility
   structure, keyboard focus, console errors, and failed requests. Exercise no
   mutating controls.
6. Capture only the two named images beneath `.local/ux-review/`. Never include
   an operator token, private identifiers, or living-system configuration.
7. Return at most five findings ordered by user impact. For each finding,
   include `OBSERVED` evidence, viewport, consequence, and one specific
   improvement. Separate blockers from polish and end with image paths plus a
   compact acceptance matrix.

## Boundaries

- Review and report only. Do not edit, stage, commit, push, publish, deploy, or
  grant release approval unless the user separately asks for implementation.
- Do not contact HYDROS or any non-loopback origin.
- Do not enter an operator token. If authentication blocks the requested
  surface, ask the operator to establish the local session and then continue.
- Label unexercised browsers, devices, screen readers, contrast measurements,
  and formal WCAG conformance `NOT TESTED`.
- Treat screenshots and browser observations as local evidence, never as
  release approval.
