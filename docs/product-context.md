# Product Context

ReefProof is configuration assurance for living systems.

Its product direction is to normalize explicit evidence, construct a
system-wide reliability model, evaluate authored safety invariants, retain
supporting evidence, and notify a human when configuration becomes unsafe.

HYDROS remains runtime authority. ReefProof may observe, model, challenge, and
alert on a living system. It may not silently take control of one.

ReefProof v0.1.0 works offline with bundled authored fixtures, manual evidence,
and operator-supplied files. It may normalize those inputs, evaluate invariants,
store evidence, and produce reports. It may not connect to HYDROS, change
outputs, modes, schedules, firmware, or configuration; perform automatic
remediation; expose general-purpose mutation APIs; or publish to MQTT.

Read-only behavior must eventually be supported by structural tests, including
negative tests. Documentation alone will not prove the boundary.

The v0.1.0 capability is offline with respect to equipment: deterministic
snapshots, typed reliability graphs, three-state invariant evaluation, durable
evidence, a local or private-LAN LXC-hosted Workbench, standalone and OCI
artifacts, and an unsigned dual-mode macOS desktop package.
No live HYDROS transport, polling, or live notification delivery is claimed.

The v0.1.0 product is an assurance workbench with a discoverable CLI, versioned
manual evidence, authenticated local and private-LAN LXC hosting profiles, safe
SQLite workflows, and a dual-mode desktop shell. Every evidence path is
explicitly offline, mock, authored, or manual. HYDROS/AWS observation is
deferred to v0.3 behind an
accepted, owner-authorized transport design. See
[`docs/release-criteria.md`](release-criteria.md).
