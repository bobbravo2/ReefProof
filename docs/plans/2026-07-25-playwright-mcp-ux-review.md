# Playwright MCP visual and accessibility review harness

Status: Structurally implemented; real MCP browser pass not tested.

## Outcome

Provide a reproducible, loopback-only browser harness for a focused advisory
sub-agent to produce UX critique ideas and deterministic release-candidate
images.

## Scope and non-goals

- Pin the official Playwright MCP development dependency and browser setup.
- Configure project-scoped Codex MCP access, isolated browser state, exact
  loopback request filtering, ignored evidence output, and a read-only reviewer.
- Define one desktop and one narrow viewport with bounded review evidence.
- Do not change product behavior, contact HYDROS, automate remediation, claim
  WCAG conformance, or grant release approval.

## Risks

- The upstream allowed-origins option does not cover redirects and is not a
  security boundary; a page-level request guard must reject every other origin.
- Browser or MCP updates may change output or accessibility snapshots; the
  package is exact-pinned and requires explicit maintenance.
- Screenshots may capture private evidence; the output directory is ignored and
  the workflow is limited to the Mock Collective fixture.

## Evaluation

- `npm test`
- `./node_modules/.bin/playwright-mcp --version`
- A real loopback desktop/mobile review after Chromium is installed
- `make check`

## Completion criteria

- A new trusted Codex session exposes the repository-local MCP server.
- Structural tests prove exact pinning, isolated execution, ignored output, and
  exact-origin request/redirect filtering.
- The reviewer emits at most five prioritized findings, two named images, and a
  bounded acceptance matrix without editing product files.
- Existing quality gates pass.

## Open questions

- Real MCP image, console, network, and redirect-blocking behavior remains to
  be observed in a fresh Codex session. A direct headless Chromium verification
  attempt crashed on the host and produced no accepted evidence.
