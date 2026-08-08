# Offline HYDROS Import Acceptance

This local-only checklist verifies faithful offline ingestion. It does not
accept undocumented HYDROS semantics, modeled relationships, configuration
safety, live transport, or equipment authority.

## Preconditions

- Work only in operator-controlled, Git-ignored storage.
- Preserve the original export bytes; do not repair, reformat, or overwrite the
  source.
- Record the export mechanism and timezone-aware capture time independently.
- Do not paste the export, normalized snapshot, identifiers, names, network
  data, credentials, or physical annotations into issues, chats, commits, logs,
  or fixtures.
- Use a synthetic secret-bearing fixture for automated redaction tests; never
  turn a private export into a test fixture.

## Deterministic import

Choose local paths without embedding them in repository documentation:

```bash
REEFPROOF_HYDROS_EXPORT='/operator/private/input.json'
REEFPROOF_CAPTURED_AT='YYYY-MM-DDTHH:MM:SS-04:00'
REEFPROOF_ACCEPTANCE_DIR="$(mktemp -d)"
```

Record the source hash without displaying content, then normalize the same
bytes twice:

```bash
shasum -a 256 "$REEFPROOF_HYDROS_EXPORT"

./reefproof snapshot \
  --hydros-export "$REEFPROOF_HYDROS_EXPORT" \
  --captured-at "$REEFPROOF_CAPTURED_AT" \
  --output "$REEFPROOF_ACCEPTANCE_DIR/first.snapshot.json"

./reefproof snapshot \
  --hydros-export "$REEFPROOF_HYDROS_EXPORT" \
  --captured-at "$REEFPROOF_CAPTURED_AT" \
  --output "$REEFPROOF_ACCEPTANCE_DIR/second.snapshot.json"

cmp "$REEFPROOF_ACCEPTANCE_DIR/first.snapshot.json" \
  "$REEFPROOF_ACCEPTANCE_DIR/second.snapshot.json"
```

`cmp` must succeed without output. Confirm the reported configuration hash
matches the original byte hash and both runs report identical provenance,
capture time, snapshot hash, entity counts, and completeness warnings.

## Privacy and semantic checks

- Normalized output, stdout, logs, APIs, Workbench views, and fixtures contain
  no credentials, account identifiers, network identifiers, or other seeded
  secret values.
- Every retained vendor field is explicitly allowlisted or represented by a
  safe hash/source reference with redaction metadata.
- Unvalidated semantics and relationships remain `UNKNOWN`.
- No result implies that the configuration or equipment is safe.
- The import performs no network request and constructs no HYDROS transport.

Record either `ACCEPT RAW IMPORT ONLY` or `REJECT RAW IMPORT` in protected local
operator evidence. Semantic acceptance requires an independently known field,
a sanitized representative test, its exact raw source path, and a separately
recorded human decision. Accepting one mapping does not accept other fields or
the system as a whole.

Remove only the known temporary acceptance directory after review. Retain the
protected original according to the operator's evidence policy.
