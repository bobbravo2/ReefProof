# Responsive rule-driven workbench

Status: Completed locally

## Outcome

Make `/workbench` a responsive, task-first rule authoring experience whose
browser model is bounded by the existing committed backend contracts and whose
canonical API namespace is `/v1/workbench`.

## Scope and non-goals

- Pair page `/workbench` with canonical API paths beneath `/v1/workbench`.
- Preserve existing request and response models. Delete `/api/workbench/*`;
  there are no public consumers and no deprecation period.
- Render the field journey, invariant catalog, physical twin, and findings from
  the existing typed API responses instead of duplicating backend data in HTML.
- Generate a checked-in TypeScript contract from FastAPI OpenAPI with an
  exact-pinned development tool and fail checks when generated output drifts.
- Put the primary authoring journey before supporting evidence, add a skip link,
  a truthful empty state, responsive reflow, visible focus, and usable targets.
- Derive the visual palette and browser favicon from the accepted ReefProof
  v0.1 logo while keeping severity meaning textually redundant.
- Do not add a general schema language, change rule semantics, contact HYDROS,
  mutate controller state, or change any request or response payload.

## Risks

- The public namespace is selected before public consumers exist, avoiding a
  compatibility burden.
- Dynamic rendering could accept unexpected backend fields; the browser rejects
  unknown, missing, or duplicate field names against a finite presentation map.
- The generator adds a development-only dependency tree; it does not ship in
  Python, standalone CLI, or OCI runtime artifacts.
- A visual redesign could obscure provenance or severity; both remain redundant
  in text and structure.

## Evaluation

- `uv run pytest tests/integration/test_api.py`
- `npm test`
- `node --test tests/web/playwright_mcp_harness.test.cjs`
- One real loopback desktop/mobile UX review
- `make check`

## Completion criteria

- `/workbench` consumes only `/v1/workbench/*` and every canonical API path
  shares the page path after the version prefix.
- Every `/api/workbench/*` path returns 404; no compatibility alias exists.
- Backend field order and catalog contents bound the visible UI.
- No saved revision is a visible empty state without a console error.
- Primary inputs precede supporting evidence at desktop and narrow viewports.
- Keyboard focus is visible, the task has a skip target, and interactive targets
  are at least 44 CSS pixels where the layout controls them.

## Open questions

- Formal browser/mobile/accessibility acceptance remains a separate human product
  decision; this slice gathers advisory evidence only.
