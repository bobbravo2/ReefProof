# Development Serve Reloader

Status: Implemented WIP for source development, preserved and excluded from
current v0.1 release claims.

## Outcome

`reefproof serve` automatically restarts after local source, template, static
asset, or configuration changes in development, while production never starts
the watcher.

## Scope and non-goals

- Add an explicit `REEFPROOF_ENVIRONMENT=development|production` runtime
  boundary.
- Default local source-checkout use to development and the OCI image to
  production.
- Allow `--reload/--no-reload` as a local developer override, except that
  production always disables reload.
- Use a small polling watcher without adding a dependency.
- Do not change API behavior, canonical state, device authority, or deployment
  exposure.

## Risks

- Rebuilding the application must release the old listener before starting the
  replacement.
- SQLite files and generated local evidence must never trigger reload loops.
- A watcher must not run in the production container.

## Evaluation

- Focused CLI tests prove option and environment behavior.
- Focused runtime tests prove relevant files trigger restart and irrelevant
  files do not.
- `make check` is the integration gate.

## Completion criteria

- Development `serve` reports and enables the watcher.
- Python, HTML, CSS, JavaScript, TypeScript, YAML, and JSON changes under the
  bounded source/configuration roots request a graceful restart.
- Production reports reload disabled even if `--reload` is supplied.
- No new dependency is added.

## Open questions

None for this slice.
