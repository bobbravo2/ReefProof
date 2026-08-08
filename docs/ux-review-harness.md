# Playwright MCP UX review harness

This local harness gives the repository-owned `reefproof-ux-review` skill enough
real-browser evidence to propose visual and accessibility improvements and
capture release-candidate images. Its findings are advisory. They do not
approve a release or establish WCAG conformance.

## One-time setup

Install the pinned development dependencies and Chromium:

```console
npm ci
npm run ux:install-browser
```

Codex reads the project-scoped MCP definition from `.codex/config.toml` after
the repository is trusted and a new session is started. The server itself runs
with:

```console
npm run ux:mcp
```

The MCP browser is isolated and headless. Both the upstream origin allowlist
and `scripts/playwright-mcp-loopback-guard.cjs` restrict requests to the exact
origin `http://127.0.0.1:8787`. The second guard also aborts non-loopback
redirect targets; the upstream allowlist alone is not a security boundary.

## Focused review

Start the application separately:

```console
REEFPROOF_BOOTSTRAP_SECRET="$(openssl rand -hex 32)" \
  uv run reefproof serve --no-open
```

Then ask the main writer with ordinary language such as:

```text
UX review the running Mock Collective Workbench. Return prioritized visual and
accessibility improvement ideas and capture the two defined release images.
```

Requests such as “UX critique,” “usability review,” and “help with a usability
critique” also invoke the skill. A new trusted Codex session is required after
adding or changing the repository skill or MCP configuration.

The skill uses only two acceptance viewports:

| View | Viewport | Image |
| --- | --- | --- |
| Desktop | 1440 x 1000 | `.local/ux-review/reefproof-workbench-desktop.png` |
| Narrow mobile | 390 x 844 | `.local/ux-review/reefproof-workbench-mobile.png` |

The bounded pass checks hierarchy, legibility, density, responsive reflow,
focus order and visibility, accessible names and roles, keyboard reachability,
status/severity redundancy, provenance, error clarity, and obvious contrast or
touch-target risks. Console errors and failed browser requests come from the
same browser session; no Electron wrapper or second embedded Chromium runtime
is required. It returns no more than five prioritized improvement ideas and a
compact acceptance matrix.

## Evidence boundary

`.local/ux-review/` is ignored and may contain generated screenshots and MCP
diagnostics. Review images before copying selected PNGs into a tracked release
location. Never capture an operator token, private identifiers, living-system
configuration, or live controller data.

Report browser and viewport observations as `OBSERVED`. Treat other browsers,
physical devices, screen readers, contrast measurement, and formal WCAG
conformance as `NOT TESTED` unless separately exercised. A clean review is not
release approval.

A human reports observing an LLM exercise the live redirect guard. Record that
as `OBSERVED`, not as a deterministic automated check; the structural Node test
remains the reproducible local substitute.
