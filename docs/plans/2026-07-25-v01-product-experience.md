# v0.1 Local Assurance Workbench

Status: Historical plan; reachability and authentication details are superseded
by ADRs 0004 and 0007 and the current v0.1.0 release criteria.

## Outcome

Deliver the v0.1 local assurance workbench defined in
[`docs/release-criteria.md`](../release-criteria.md): usable CLI help,
versioned web rule authoring, a mocked mobile-friendly physical digital twin,
safe SQLite workflows, and a clear first-time path to value.

## Scope

- Standalone CLI help and first-run experience.
- Rule revision model, validation, deterministic preview, and tree-based web
  authoring interface.
- Mocked physical-layer digital twin with SVG-compatible assets, severity
  rendering, and an extensible, reviewable agent proposal interface.
- Safe database inspection, backup, restore, verification, and rule workflows.
- Mobile and accessibility acceptance evidence.

## Accepted interview decisions

- The v0.1 quick path is a guided mocked starter followed by a short manual
  collective-model form. It must visibly label the resulting model as
  mock/manual rather than live observation.
- The first journey is circulation-oriented and progressively captures the
  main-tank return flow rate in gallons per hour (GPH). It uses the fixed
  identity `Mock Collective`; naming is deferred. HTML, typed API data, saved
  revisions, and previews must retain `MANUAL / NOT LIVE`.
- The original v0.1 rule-editor slice was loopback-only and intended for one local operator.
  A secret supplied only through `REEFPROOF_OPERATOR_TOKEN` is exchanged for
  an opaque, process-local frontend session ID. Saved revisions retain that
  session ID as non-secret author attribution; the token is never persisted.
  ADR 0007 later added the explicit private-LAN LXC-hosted profile without
  adding application accounts or public ingress.
- The initial v0.1 rule builder uses approved templates for the existing
  fifteen invariants and renders their logical-tree previews. A general visual
  rule language is out of scope for the first slice.
- The web interface uses FastAPI-rendered Jinja2 templates and strict
  TypeScript compiled into external files with cache-busted URLs. It does not
  put application behavior in inline scripts.
- The backend is authoritative: typed state and events flow from backend to
  frontend, and edits return through explicit ReefProof policy endpoints. The
  seam must support a future backend-to-browser WebSocket stream for v0.3
  HYDROS-derived events without exposing MQTT or HYDROS directly to browsers.
- v0.2 adds a read-only local viewing profile alongside offline/mock local
  authoring and makes local developer/operator rule-tree revisions visible.
  It remains offline; live HYDROS observation begins in v0.3.

## Non-goals

- Live HYDROS/AWS retrieval, MQTT publication, controller mutation, automatic
  remediation, or any use of owner credentials.
- Selecting a client-side UI framework, WebGL library, editor component, or
  agent runtime before the first vertical slice demonstrates the need.
- Publishing community posts or making any external communication.

## Risks

- A visual rule editor can obscure rule semantics; deterministic text/tree
  rendering and preview evidence must remain authoritative.
- An agent extension path could silently expand model semantics; proposals must
  remain validated, attributable, and human-reviewed.
- Web/mobile work may accidentally turn mock configuration into a live-system
  claim; every mock screen and exported artifact needs explicit provenance.

## Evaluation

- Binary smoke checks for help, version, and first-run workflow.
- Rule round-trip, validation, revision, preview, and backup/restore tests.
- API/UI tests for logical-tree rendering, severity accessibility, and mobile
  viewport interaction.
- Digital-twin rendering fixtures, extension-interface validation, and proof
  that it cannot reach a HYDROS mutation path.
- Existing `make check`, hardened OCI checks, and supply-chain release checks.

## Completion criteria

- All v0.1 criteria in `docs/release-criteria.md` have current evidence.
- The exact invariant set and mock/manual onboarding policy are accepted.
- A first-time user can reach an understandable safety result without
  credentials, a network connection, or a live collective.
- Rule and visual authoring changes remain limited to ReefProof-owned state.

## Open questions

- Which browser support, mobile viewport, and accessibility targets define
  v0.1 acceptance?
