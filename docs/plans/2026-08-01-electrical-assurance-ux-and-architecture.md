# Electrical assurance UX and architecture

Status: Planned from expert interview and the first real offline HYDROS export.

## Outcome

Make ReefProof v0.1 prove one complete, read-only electrical-assurance slice
from the operator-supplied HYDROS export: preserve byte-faithful raw evidence,
produce a secret-safe normalized snapshot, resolve the represented controller
and physical-port topology, reconcile it with separately authored Reliable Reef
intent, and explain one materially useful deterministic result.

The initial Workbench experience is a system-level electrical posture brief.
It must make incomplete coverage conspicuous and guide the operator from missing
mapping to trusted finding without presenting inference as observation.

## Ground truth and claim boundary

The private export and its existing generated snapshot are the acceptance
evidence for this plan. They contain one collective, nine devices, five inputs,
eight configured outputs, one Wi-Fi power strip, and six modes. They contain no
heater output, authored entities, or annotations. The snapshot is observed
configuration evidence, not an annotated digital twin.

The export may remain only in the protected local raw-evidence store. Tests use
purpose-built synthetic fixtures containing representative secret-bearing keys
and vendor references; neither the private export nor derived private
identifiers enter the repository.

The first result is:

> HIGH-CONCERN UNKNOWN — Automatic load shedding is not proven

Tiered modes are observed, but no automatic low-power trigger is represented.
This remains `UNKNOWN` until authored trigger intent and the relevant HYDROS
semantics exist. An unused `lowPower` field alone is not a failure.

`maxOnTime: 0` on the observed RODI output initially produces:

> UNKNOWN — Maximum RODI actuation duration cannot be established

Only an accepted semantic mapping that establishes zero as disabled or
unbounded can support comparison with authored intent and a possible HIGH
finding. Heater invariants remain authored/test-fixture coverage and stay out
of operator-visible evaluation until a later heater-bearing export exists.

## Scope

- Import the exact bytes offline and retain their SHA-256 identity and capture
  timestamp in a protected evidence store.
- Normalize only allowlisted, non-secret vendor fields. Retain source paths,
  field-level provenance, redaction markers, and hashes without copying secrets,
  network identifiers, or account identifiers.
- Promote friendly device names and stable hardware identities while retaining
  deterministic ReefProof IDs.
- Create first-class physical port and outlet entities and resolve supported
  device, input, output, dependency, mode, and safe-state relationships.
- Keep observed HYDROS relationships distinct from authored physical-power and
  protection mappings.
- Add authored circuit, breaker/GFCI, backup-power, load-limit, supported
  function, and operator-confirmed mapping evidence.
- Evaluate tiered load shedding only against explicit authored intent.
- Redesign the Workbench around electrical posture, coverage, mappings,
  findings, evidence drill-down, and operator verification.
- Persist acknowledgements, exceptions, and verification evidence without
  changing or rewriting the underlying observed snapshot.
- Refactor importer, graph, evaluation, persistence, and browser presentation
  around narrow reusable contracts rather than adding more special-case page
  logic.

## Non-goals

- Live HYDROS transport, polling, MQTT publication, controller mutation,
  equipment commands, configuration changes, or automatic remediation.
- Inferring branch circuits, protection, backup power, supported function, or
  load limits from names such as `XP8-Main6` and `XP8-Main8`.
- Claiming heater assurance from this export.
- Treating `maxOnTime: 0`, `lowPower`, or other undocumented vendor values as
  understood before their semantics are accepted.
- Chemistry evaluation, time-series chemistry envelopes, or aquarium-health
  alerting in v0.1.
- A generic vendor schema language, generic graph database, unrestricted SQL
  interface, or speculative plugin framework.

## Domain model

ReefProof maintains two linked graphs.

### Physical power graph

`source -> panel -> branch circuit -> protection -> controller/distribution device -> physical outlet/port -> powered equipment -> supported function`

Circuit, breaker/GFCI, UPS, generator, and load-limit facts are authored or
explicitly operator-confirmed. Vendor names are matching hints only.

### HYDROS control graph

`collective -> device -> physical port -> configured output -> sensor/input -> dependency -> operating mode -> safe state`

Vendor references such as `4$ac5`, `3$force2`, and named Wi-Fi-strip outlets
resolve to first-class port/outlet nodes. Resolution retains the original safe
source path and never silently converts a matching hint into an authored fact.

Edges can carry observed or authored provenance. Shared-failure domains include
branch circuit, breaker/GFCI, distribution device, collective/bus, sensor,
upstream flow, network dependency, and backup-power source.

Each interpreted property records its value, source path, semantic definition
and version, provenance, and field-level confidence. Any inference remains
`UNKNOWN` unless its required evidence is provable or an operator explicitly
accepts the unresolved/contradictory condition under a versioned policy.

## Extensible and DRY architecture

Keep vendor parsing, canonical evidence, reconciliation, evaluation, and UI
projection separate:

1. **Raw evidence boundary** reads bytes, computes identity, and stores the
   protected artifact. No downstream contract requires access to raw bytes.
2. **HYDROS adapter** extracts records through explicit allowlists and a
   centralized redaction policy. A single reference parser resolves vendor
   device/port syntax; import paths do not duplicate string parsing.
3. **Canonical evidence model** represents entities, ports, interpreted
   properties, relationships, provenance, confidence, and source references
   independently of HYDROS payload shape.
4. **Intent overlay** versions authored Reliable Reef entities and mappings.
   It links to observed evidence but never overwrites it.
5. **Reconciler** produces typed coverage gaps, unresolved references, and
   contradictions from observed and authored graphs.
6. **Invariant engine** consumes only canonical evidence plus authored intent;
   rules do not parse vendor JSON or query browser state.
7. **Finding projection** supplies one reusable finding/drill-down model to CLI,
   API, persistence, and Workbench. Presentation code does not reconstruct
   evaluation meaning.
8. **Workbench components** render typed overview metrics, mappings, findings,
   and evidence panels from generated API contracts. Shared session, status,
   provenance, empty-state, and evidence-detail rendering replaces repeated
   per-page authentication and DOM wiring.

Prefer small registries for vendor section adapters, port families, interpreted
field semantics, relationship resolvers, and invariant definitions. Each
registry entry must have immediate acceptance evidence from this export or a
clearly labeled authored fixture; do not build unused extension points.

## Iterative implementation plan

### Iteration 0 — freeze evidence and leakage tests

- Record safe aggregate expectations and the known reference examples without
  copying the private payload into tests or documentation.
- Add a synthetic Tuya-shaped fixture with fake credentials, local/public
  network identifiers, and account identifiers.
- Build a recursive normalization escape test that searches the complete
  normalized object, serialized snapshot, logs, CLI output, and Workbench/API
  projection for seeded secret values.
- Establish a deny-by-default sensitive-key policy plus an allowlist for the
  few non-secret Tuya properties required for topology.

Gate: no secret-bearing value from the synthetic record can leave the protected
raw-evidence boundary. This is an independent v0.1 release blocker.

### Iteration 1 — byte-faithful raw evidence and safe normalization

- Separate raw artifact persistence from parsed normalization.
- Preserve raw hash, snapshot hash, capture timestamp, parser warnings, and a
  redaction manifest that reports paths and categories, never redacted values.
- Replace wholesale `vendor_extensions` copying with safe projections.
- Promote friendly names and stable hardware identifiers with field-level
  source paths and confidence.
- Prove deterministic output across repeated imports and prove byte changes
  affect raw identity even when parsed JSON is equivalent.

Gate: the exact private export imports offline, aggregate counts match the
accepted ground truth, normalized output is deterministic, and the leakage
test remains green.

### Iteration 2 — first-class port and control topology

- Add canonical port/outlet entities with controller ownership and port-family
  metadata.
- Implement one reusable HYDROS reference parser/resolver for numeric device
  references, AC/drive/force ports, and Wi-Fi-strip outlet references.
- Preserve unresolved and ambiguous references as explicit coverage gaps.
- Represent observed ownership and dependency edges with source-backed
  provenance; update graph types so observed edges are possible without
  weakening authored-evidence requirements.
- Report resolved/unresolved counts and retain shared-failure-domain candidates
  without inferring circuits from device names.

Gate: every provided reference example resolves to the accepted device and
physical port, malformed/unknown references fail closed, and no circuit or
protection mapping is inferred.

### Iteration 3 — authored electrical intent and reconciliation

- Add versioned authored entities for source, panel, circuit, protection,
  backup power, load limits, equipment, supported function, and desired safe
  state.
- Add operator mappings that link authored entities to observed devices/ports
  while preserving both identities and provenance histories.
- Validate graph integrity, prevent accidental observed-fact overwrite, and
  expose contradictions as explicit reconciliation records.
- Model coverage for circuit, GFCI, UPS/generator, load limit, sensor, upstream
  flow, network, and distribution-device failure domains.

Gate: an operator can complete, revise, acknowledge, and re-inspect mappings;
observed evidence remains immutable and missing authored coverage remains
`UNKNOWN`.

### Iteration 4 — tiered-load-shedding assurance

- Version the authored requirement for automatic versus manual load shedding.
- Interpret tier/mode semantics only through accepted mappings with explicit
  confidence.
- Evaluate observed tiers, known exclusions, trigger evidence, authored intent,
  and verification history through one deterministic invariant.
- Emit HIGH-CONCERN `UNKNOWN` for the accepted initial state, including risk,
  missing evidence, and the five-step verification procedure.
- Add the conditional RODI runtime invariant, keeping it `UNKNOWN` until zero
  semantics are verified.
- Keep heater invariants dormant for this snapshot and exercise them only with
  clearly authored fixtures.

Gate: the same canonical inputs produce the same result and explanation through
unit, API, CLI, persistence, and packaged-runtime paths; no unsupported FAIL or
heater claim is possible.

### Iteration 5 — task-first electrical Workbench

- Replace the generic landing emphasis with a system-level electrical posture
  brief stating that the import is partial and naming the unproven domains.
- Show device/port topology, resolved versus unresolved connections, authored
  versus observed coverage, criticality modes/exclusions, protection and backup
  coverage, freshness, `UNKNOWN` count, and highest-value verification.
- Make **Complete electrical mappings** the first action until sufficient
  authored coverage exists; then promote **Review highest-consequence finding**.
- Separate safe evaluation from persistence: review a deterministic result
  before deliberately recording acknowledgement, exception, or verification.
- Authenticate once per Workbench session and reuse shared loading, error,
  provenance, and empty-state components.
- Use operator-language summaries first and place IDs, reason codes, and raw
  paths in technical disclosure sections.

Gate: source and browser acceptance demonstrate that an operator can move from
partial import to missing mapping, finding, source evidence, verification steps,
and persisted acknowledgement without encountering a control path.

### Iteration 6 — trusted drill-down and packaged acceptance

Every finding exposes:

1. affected device, port, output, and supported function;
2. original source path and safely redacted source values;
3. raw configuration hash and capture timestamp;
4. authored requirement and version;
5. interpreted HYDROS semantics and confidence;
6. deterministic evaluation logic;
7. missing evidence responsible for `UNKNOWN`;
8. shared-failure-domain context;
9. remediation and verification procedure; and
10. acknowledgement, exception, and operator-verification history.

Exercise the same workflow from the local web server, standalone CLI, and
packaged macOS desktop application. Packaging must use current-commit assets
and must not broaden renderer or runtime authority.

Gate: the exact v0.1 acceptance criteria below pass from a clean checkout and
private evidence remains outside source, build logs, normalized fixtures, and
packaged UI assets.

## UX content contract

For the accepted export, the posture brief begins:

> Partial electrical configuration imported. RODI and mixing-room equipment
> are represented. Display heating, primary returns, circuit protection,
> backup power, and authored electrical mappings are not yet proven.

The page distinguishes:

- **OBSERVED:** source-backed configuration and point-in-time evidence;
- **AUTHORED:** versioned Reliable Reef intent and operator mappings;
- **INFERRED:** explicitly identified derived statements;
- **UNKNOWN:** missing, unverified, contradictory, or inference-dependent facts;
- **VERIFIED:** operator-recorded test evidence with timestamp and scope.

No empty state, badge color, or optimistic default may turn missing evidence
into PASS.

## Evaluation strategy

- Unit tests for sensitive-key classification, allowlisted projection, stable
  IDs, port parsing/resolution, confidence derivation, reconciliation, and each
  invariant branch.
- Property/parameterized tests for nested secret-bearing values, unusual key
  casing, malformed vendor references, ambiguous owners, and deterministic
  ordering.
- Golden normalized snapshots use only synthetic data and assert semantic
  structure rather than copying the private export.
- Integration tests cover raw-store separation, snapshot persistence, authored
  overlay, finding history, API contracts, and restart-stable replay.
- Browser tests cover posture comprehension, keyboard navigation, responsive
  topology, progressive disclosure, `UNKNOWN` prominence, and the mapping-to-
  verification workflow.
- Packaged acceptance verifies the current-commit binary, local-only loading,
  secret absence, renderer sandbox, and clean process shutdown.
- The final repository gate uses the repository-owned local-CI workflow. Agent
  benchmarks, publication, live HYDROS access, and deployment are excluded.

## v0.1 completion criteria

ReefProof can:

- import the exact imperfect export and preserve/hash the protected raw bytes;
- produce a deterministic normalized snapshot without leaking secrets;
- resolve represented HYDROS physical ports and report unresolved references;
- overlay authored electrical intent without overwriting observed facts;
- explain at least one deterministic PASS, FAIL, or UNKNOWN result;
- guide the operator through a concrete verification;
- persist acknowledgement or verification evidence append-only;
- expose the complete trusted drill-down; and
- remain structurally read-only toward HYDROS.

## Risks and stop conditions

- If safe versus secret Tuya fields cannot be classified confidently, retain
  only a blob hash and redaction metadata; do not normalize the blob.
- If a vendor reference is ambiguous, emit an unresolved-reference record; do
  not select the most likely device or port.
- If `lowPower`, `maxOnTime`, modes, dependencies, or safe-state semantics are
  unverified, stop at `UNKNOWN`.
- If authored and observed facts conflict, preserve both and require explicit
  reconciliation; never overwrite history.
- If this design requires a live HYDROS connection or write-capable transport,
  stop. It is outside v0.1 and outside this plan.
- Large generic abstractions are rejected unless two immediate in-scope uses
  demonstrate the duplication they remove.

## Open questions

- Which safe Tuya properties, if any, are required to resolve the observed
  Wi-Fi power-strip topology?
- What authoritative HYDROS documentation or operator test establishes the
  semantics of `lowPower`, `maxOnTime`, mode exclusions, and unavailable input
  behavior?
- What exact authored circuit/protection/backup mapping format is easiest for
  the operator to maintain and version?
- Which verification evidence types are required beyond a timestamped operator
  acknowledgement for the first load-shedding test?
- Chemistry envelopes, drift, and long-horizon stability remain deferred to
  later roadmap milestones.
