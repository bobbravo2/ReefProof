# Multipage Workbench and Evidence

## Outcome

Split the local ReefProof workbench into distinct full-page routes for Overview,
System Map, Assurance, Evidence, and Sessions. Make Evidence the clearest place
to inspect authored revisions, the executable invariant catalog, provenance,
and the limits of what the current offline model proves.

## Scope and non-goals

In scope:

- Keep `/workbench` as the Overview entry point.
- Add `/workbench/system-map`, `/workbench/assurance`,
  `/workbench/evidence`, and `/workbench/sessions`.
- Use real navigation links with an explicit current-page state.
- Load only the backend data required by the current page.
- Preserve the existing manual return-flow authoring flow on Assurance.
- Preserve the authored physical twin on System Map.
- Improve Evidence with an authored-revision summary, catalog explorer, and
  conspicuous provenance and proof-boundary language.

Out of scope:

- New controller, MQTT, HYDROS, or other network integration.
- Automatic remediation or any expansion of write authority.
- New authentication, project-state API, or session-management behavior.
- Changing the invariant catalog or physical model.

## Risks

- Existing deep links using page fragments can still open `/workbench`, but
  their former sections move to dedicated routes.
- Splitting one document can expose hidden browser assumptions in the current
  TypeScript initializer.
- Evidence language could imply live observation unless manual provenance and
  non-live boundaries remain explicit.

## Evaluation

- Add route-level integration coverage for status, navigation, page isolation,
  asset loading, and Evidence semantics.
- Extend the browser contract test to prove page-specific initialization and
  saved-revision evidence rendering.
- Run the registered strict TypeScript and web tests, focused API tests, and
  `make check`.
- Capture bounded desktop and mobile visual/accessibility evidence through the
  read-only ReefProof UX reviewer.

## Completion criteria

- All five full-page routes return successfully and identify the active route.
- Each route contains only its relevant primary workflow.
- Evidence explains what is authored, what is executable, and what is not live.
- Evidence handles the absence of a saved revision without presenting an error.
- No v0.1 authority or transport boundary changes.
- Focused and broad local evaluations pass.

## Open questions

- Whether later authenticated project sessions should replace the current
  informational Sessions page remains deferred to the planned project API.
- Whether legacy fragment links should redirect to their new routes can be
  decided after observing actual local usage; no compatibility redirect is
  required for the current private workbench.
