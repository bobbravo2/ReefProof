# ADR 0002: No MQTT Publication in v0.1

- Status: Accepted
- Date: 2026-07-25
- Decision owners: ReefProof maintainers
- Scope: All ReefProof v0.1 runtime and research code

## Context

ReefProof is an assurance plane for a living system. HYDROS remains runtime
authority, and ReefProof must not silently acquire control-plane capability.

Some HYDROS status-streaming behavior may require an MQTT `PUBLISH` request
before responses begin. The proposed product brief described a narrow exception
for an exact empty status-listening request. Even a narrow publisher, however,
introduces a write-capable primitive into a safety-sensitive runtime before its
protocol effects and authorization boundary are established.

The repository's existing permanent boundary prohibits MQTT publication in
v0.1. This ADR accepts and makes that boundary precise.

## Decision

ReefProof v0.1 sends no MQTT `PUBLISH` packet.

This prohibition includes:

- Empty or non-empty status-listening requests.
- Requests intended only to trigger a response.
- Retained and non-retained messages.
- Arbitrary topic or payload publication.
- Output, mode, schedule, firmware, membership, and configuration commands.
- Test, diagnostic, keepalive-like, or protocol-research publications against
  any live broker.

ReefProof v0.1 exposes no generic MQTT publish interface, no specialized
status-request publisher, and no mutation command constructor.

If a status stream requires an MQTT publication to activate it, that stream is
unavailable to v0.1. ReefProof must use an independently accepted read-only
observation mechanism, such as conservative configuration retrieval.

## Meaning of "no MQTT writes"

For this decision, a write means an MQTT application `PUBLISH` packet.

A future accepted transport may send the minimum protocol control traffic
needed to establish a read-only subscription, including `CONNECT`,
`SUBSCRIBE`, acknowledgements, and disconnect traffic. Those control packets do
not authorize an application publication.

Subscription is not approved by this ADR. It remains subject to a separate
transport decision, credential-scope review, protocol evidence, and structural
tests.

## Structural requirements

Before any MQTT observation code enters v0.1:

- The ReefProof transport protocol must contain no publish operation.
- Product code must not receive an object exposing a publish method.
- Topic construction must be closed to an explicitly approved response-topic
  allowlist.
- Credentials and broker policy must be read-only where the platform supports
  that distinction.
- Tests must prove ReefProof cannot construct or send a `PUBLISH` packet.
- Static or dependency-boundary checks must detect newly reachable publication
  primitives.
- Fixture and fake-broker tests must cover observation without a live system.

A library that also implements publication may be used only if the accepted
transport design makes that capability structurally unreachable from the
ReefProof runtime and the negative tests demonstrate the boundary. Naming a
wrapper "read-only" is insufficient.

## Consequences

### Positive

- The runtime cannot send a status request that is later discovered to have
  state-changing effects.
- A compromised or confused product call site has no MQTT application-write
  primitive.
- v0.1 safety claims remain simple and testable.
- Polling or another retrieval mechanism can deliver assurance value before
  reverse-engineered streaming is trusted.

### Costs

- Status streaming may be unavailable even if upstream research code supports
  it.
- Detection latency may be bounded by a vendor-safe polling interval.
- MQTT-triggered or hybrid observation is deferred beyond v0.1 unless this ADR
  is explicitly superseded.

## Superseding this decision

Changing this boundary requires a new accepted ADR. That ADR must include:

- Redacted, repeatable protocol evidence.
- A threat model for the exact topic, payload, credentials, and broker policy.
- Proof that the operation cannot change controller or broker-retained state.
- An interface that cannot express arbitrary topics or payloads.
- Structural negative tests and an independent security review.
- A clear user-visible benefit that cannot be achieved safely through
  read-only retrieval.

Protocol convenience alone is not sufficient.

## Related decisions

- `AGENTS.md`: permanent product invariant and v0.1 prohibition on MQTT
  publication.
- `docs/adr/0001-proposed-product-architecture-and-safety-boundary.md`:
  umbrella product proposal.
- `docs/architecture-decisions.md`: accepted-decision index.
