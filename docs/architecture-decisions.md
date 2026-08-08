# Architecture Decisions

The following decisions are currently accepted:

1. HYDROS remains runtime authority.
2. ReefProof v0.1 is read-only.
3. Observed state is evaluated against authored safety invariants.
4. Evaluation results will use `PASS`, `FAIL`, and `UNKNOWN`.
5. Development begins with fixtures before live integration.
6. Repository artifacts preserve cross-session agent context.
7. Phase 0 uses Python 3.13, uv, Typer, Pydantic v2, and structlog; Pytest,
   Ruff, and Pyright provide local quality gates.
8. Agent-cost collection is local, sanitized, append-preserving for completed
   sessions, and reports unavailable metrics as `UNKNOWN`.
9. ReefProof v0.1 sends no MQTT `PUBLISH` packet, including an empty request
   intended to start status streaming. See
   `docs/adr/0002-no-mqtt-publication-in-v0-1.md`.
10. Published OCI releases use GitHub Container Registry, are Linux amd64,
    deploy by immutable digest, and use GitHub Actions OIDC/Sigstore
    attestations for provenance and SPDX 2.3 SBOM evidence. Unfixed HIGH or
    CRITICAL Trivy findings block a release.
11. v0.1 is an offline assurance workbench built on mock/manual collective models
    and deployable locally or on an explicitly configured private-LAN LXC;
    live HYDROS/AWS message reading is deferred to v0.3. Rule, digital-twin,
    and agent-extension workflows may change only ReefProof-owned policy and
    evidence, never controller state.
12. The first v0.1 authoring slice is a template-first editor for the existing
    fifteen invariants. It is loopback-only in `local-managed` mode and served
    by the authoritative LXC backend in `remote-hosted` mode. FastAPI renders Jinja2 templates;
    strict TypeScript is compiled to external cache-busted assets. Typed data
    flows from the authoritative backend to the browser, preserving a future
    backend WebSocket event seam without browser access to HYDROS or MQTT.
13. v0.2 may harden deployment, connection profiles, packaging, and controlled
    preview without adding live equipment observation. v0.3 is the first
    release that may observe live HYDROS data.
14. v0.1 rule writes and trust actions use a bootstrap shared secret plus
    authenticator app enrollment model. A configured or generated bootstrap shared secret is
    used once to establish an initial session and enroll TOTP; thereafter,
    six-digit authenticator codes establish sessions. The backend exchanges successful
    authentication for an identity-bound, signed, expiring, `HttpOnly`,
    `SameSite=strict` session cookie backed by server-side session state;
    immutable revisions store only a non-secret session identifier for author
    attribution and never store the secret or authenticator codes.
15. Explicit UI work may enable the exact-pinned Playwright MCP development
    harness with isolated browser state, an exact loopback request guard, and
    ignored local evidence. It is not configured as a default MCP server. Its
    browser observations and release-candidate images do not establish WCAG
    conformance or grant release approval.
16. Local HTML page paths map to versioned API namespaces by inserting the
    version prefix before the page path: `/workbench` consumes
    `/v1/workbench/*`. `/api/workbench/*` is deleted rather than deprecated;
    there are no public consumers requiring compatibility aliases.
17. ReefProof is a deterministic, evidence-backed project state engine with an
   intelligent interface, not a chat application. The v0.1 reference project is
    the durable v0.1 home; Overview, System Map, Assurance, Evidence, and
    Sessions are its primary areas. Typed candidate facts become canonical
    only after validation, explicit acceptance-authority approval, and an append-only domain
    event. See
    `docs/adr/0003-trustworthy-state-engine-and-project-information-architecture.md`.
18. Local authentication uses an identity-bound, signed, expiring,
    `HttpOnly`, `SameSite=strict` session cookie. Project and principal display
    labels are never authorization identity; human acceptance is authorized by
    a configured stable principal. ADR 0007 supersedes ADR 0004 only where it
    required loopback-only reachability; its identity, authorization, and
    session requirements remain in force. See
    `docs/adr/0004-identity-bound-zero-trust-sessions.md` and
    `docs/adr/0007-dual-mode-desktop-and-lan-hosted-service.md`.
19. The local workbench implements those primary areas as distinct full-page
    routes beneath `/workbench`. Evidence is the traceability surface for saved
    authored revisions, executable invariant logic, provenance, and explicit
    proof limits; Assurance retains bounded local authoring, and System Map
    retains the authored physical model. Legacy workbench fragments redirect
    client-side to their corresponding full-page route.
20. Preserved Home Assistant delivery is explicit opt-in with split authority.
    YAML may enable only the adapter type. The complete endpoint and bearer
    token come from `REEFPROOF_HOME_ASSISTANT_ENDPOINT` and
    `REEFPROOF_HOME_ASSISTANT_TOKEN`; the endpoint must use an explicit
    loopback or private IP address. Hostnames, public, link-local/metadata,
    multicast, unspecified, or reserved addresses, URL credentials, fragments,
    missing tokens, and redirects fail closed before credential forwarding.
    It is deferred from current v0.1 release claims; live delivery remains
    `NOT TESTED`.
21. The local workbench keeps `reefproof serve` as a foreground command and
    exposes detached lifecycle operations as `reefproof daemon start|stop|status`.
    The daemon uses a local PID file and detached log, observes process
    existence portably, and requests graceful shutdown without force-killing a
    timed-out process. A production service manager remains deployment
    authority.
22. Development-tool vulnerability remediation may use exact root-level npm
    `overrides` only when a live audit identifies the vulnerable transitive
    paths, the selected versions contain the upstream fixes, `npm ci` and the
    complete frontend gates pass, and the packages are absent from shipped
    Python, standalone, and OCI runtime artifacts. Overrides are reviewed
    compatibility constraints, not proof that upstream consumers support the
    forced versions; remove them when direct dependencies resolve the paths.
23. `reefproof serve` has a dependency-free, bounded polling reloader for local
    development. It watches only authored source and configuration types under
    repository `src/` and `config/`, never mutable evidence storage. The local
    environment defaults to `development`; the production OCI image explicitly
    sets `REEFPROOF_ENVIRONMENT=production`, where reload remains disabled even
    if requested. Foreground service behavior, API authority, canonical state,
    and the loopback-only bind do not change.
24. The first public release uses Python distribution and executable version
    `0.1.0`, Git tag `v0.1.0`, and matching OCI version metadata. Release
    automation fails closed when the tag and package version differ. “v0.1”
    remains prose shorthand, not a second version identity.
25. The public OCI namespace for v0.1 is
    `ghcr.io/bobbravo2/reefproof`. Published deployment inputs use an immutable
    digest; Outie/sentient remains external deployment infrastructure.
26. Projection-only trust revocation follows ADR 0006: accepted trust events
    preserve canonical facts and raw evaluations while derived projections may
    become effective `UNKNOWN / REVOKED`. The implementation is preserved as
    deferred WIP and is not part of the current proof-of-trust release claim.
27. The v0.1.0 desktop supports explicit `local-managed` and `remote-hosted`
    modes. Remote mode connects only to an operator-configured private-LAN
    ReefProof origin, supports a direct LXC IP and port, permits HTTP only for a
    validated literal private address, reuses identity-bound operator sessions,
    and runs fixed-purpose diagnostics, backup creation and download, and
    ReefProof lifecycle actions through authenticated backend APIs on the hosted service. It provides no
    general host administration or HYDROS control capability. See
    `docs/adr/0007-dual-mode-desktop-and-lan-hosted-service.md`.
28. ADR 0008 defines the exhaustive `/v1` API, authentication and authorization
    tiers, immutable mutation audit, fresh-schema behavior, and canonical v0.1
    terminology. The executable pytest contract compares every route-matrix
    column with FastAPI and OpenAPI. See
    `docs/adr/0008-versioned-api-and-terminology-contract.md`.

No technology decision has been accepted for live HYDROS transport. Future
release scope is defined only by the decisions explicitly recorded above and
the integration points in `docs/roadmap.md`.
