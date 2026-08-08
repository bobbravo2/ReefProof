# Open Questions

Only unresolved decisions belong here. Resolved release identity and the public
OCI namespace are recorded in `docs/architecture-decisions.md`.

- **Before accepting the v0.1 target LXC:** Which narrow supervisor mechanism
  permits ReefProof-only restart without general systemd, container, or host
  authority?
- **Before accepting remote backup download:** What bounded retention policy
  removes staged hosted artifacts after successful or abandoned retrieval?
- **Before accepting persisted desktop connection profiles:** Which non-secret
  mode/origin fields may persist, where are they stored, and how does origin
  change invalidate the prior session?
- **Before claiming public compatibility:** What platforms and Python versions,
  beyond CPython 3.13 on Linux and macOS, are supported?
- **Before public artifact publication:** What security-reporting channel is
  authoritative?
- **Before public package publication:** What package owner and maintainer
  metadata should be published?
- **Before a public lifecycle promise:** Does `daemon start|stop|status` become
  a compatibility contract, and on which platforms?
- **Before promoting diagnostics:** Does the read-only SQLite explorer enter a
  later release, and what exposure/usability evidence is required?
- **Before any live HYDROS claim:** What structural evidence proves the
  transport is read-only and cannot mutate configuration, equipment, or MQTT?
- **Before production polling:** What retrieval mechanism and frequency are
  vendor-supported and safe?
- **Before storing private annotations:** What storage, redaction, retention,
  and access policy applies?
- **Before treating agent cost as complete:** What stable authoritative usage
  schema supports project-level accounting without estimation?
