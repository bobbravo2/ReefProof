# ReefProof release and release-notes runbook

This is the authoritative procedure for publishing a ReefProof release and for
correcting the human-readable notes of an existing release. It supplements the
[release criteria](release-criteria.md) and
[open-source release checklist](open-source-release-checklist.md); it does not
waive target-LXC, desktop, privacy, or safety evidence.

Publishing is an external write. An agent must have explicit human authority to
push the candidate, create or push a tag, publish artifacts, or deploy them.
Release publication does not authorize deployment or live HYDROS access.

## 1. Establish the exact candidate

1. Run project grounding and inspect `git status -sb`, the current branch,
   `origin/main`, and relevant diffs.
2. Start from the public repository's current `origin/main`. Never force-push,
   reset, discard, or overwrite unexplained local history or dirty work.
3. If local and remote histories diverge, create an isolated worktree from
   `origin/main` for the candidate. Preserve the previous local tip and any
   dirty snapshot on a named archive branch before later aligning local `main`.
4. Keep one exact candidate commit. Record its full SHA; branch names and local
   image tags are not release identities.

## 2. Prepare version and human notes

For a release `X.Y.Z` and tag `vX.Y.Z`:

1. Update `pyproject.toml`, `src/reefproof/__init__.py`, `uv.lock`, and current
   product copy that states the executable version. Verify CLI, desktop, package,
   and OCI identities remain derived from the same project version.
2. Rebuild generated contracts and the tracked Workbench JavaScript with
   `npm run build`. Never edit generated JavaScript directly. Confirm
   `src/reefproof/api/web/static/workbench.js` is tracked and included by
   `scripts/build-stage.py`.
3. Copy [the release-notes template](releases/TEMPLATE.md) to
   `docs/releases/vX.Y.Z.md` and replace every placeholder. Human notes are a
   required release input, not a post-publication afterthought.

Release notes must lead with operator impact and include:

- a plain-language summary and whether the release is recommended;
- `## What changed` with user-observable behavior;
- who should install, upgrade, or avoid the release;
- upgrade or compatibility guidance, including schema and durable-data impact;
- `## Changelog` with a tag comparison link when a previous release exists;
- known issues and supersession guidance when applicable; and
- `## Safety boundary`, preserving HYDROS runtime authority.

Do not put credentials, private addresses, device identifiers, aquarium
identity, local paths, or unverified claims in release notes. Do not copy the
technical receipt into the human document. The publication workflow appends the
registry digest, source SHA, platform, SBOM, and vulnerability evidence after
the human notes.

## 3. Verify the clean candidate

Before tagging:

1. Run focused checks while iterating.
2. Run the repository-owned local-CI `local-check` task after the final source
   or documentation change.
3. Commit only reviewed paths and run `git diff --cached --check` before the
   commit.
4. From the exact clean commit, run the repository-owned `local-bundle` task.
5. Complete the secret/history scans, packaged desktop acceptance, target-LXC
   acceptance, and other evidence required by the release criteria. Report
   unavailable evidence as `NOT TESTED`, never inferred `PASS`.
6. Run `uv run python scripts/verify-release-tag.py vX.Y.Z` and confirm the
   proposed tag matches the package version.

A passing source suite alone does not prove the OCI artifact, GitHub Release,
attestations, public pullability, desktop, or target-LXC deployment.

## 4. Publish through the tag workflow

After explicit publication approval:

1. Fetch `origin/main` and confirm it has not moved since candidate validation.
2. Fast-forward the reviewed candidate to public `main`; do not rewrite public
   history.
3. Create an annotated tag: `git tag -a vX.Y.Z -m "ReefProof vX.Y.Z"`.
4. Push that exact tag. Do not push an image manually.
5. Monitor `.github/workflows/release.yml` to completion. It must:
   - verify tag/package identity and human release notes;
   - pass the canonical quality gate;
   - build and scan Linux amd64;
   - publish the verified GHCR image;
   - attach provenance and SPDX attestations;
   - create the technical receipt and GitHub Release assets; and
   - combine `docs/releases/vX.Y.Z.md` before the technical evidence.
6. Also record the tag-triggered checks and delivery workflow results. A green
   release workflow does not silently convert separate failed checks to `PASS`.

## 5. Accept the published release

Verify the external result, not merely the workflow configuration:

1. Open the GitHub Release and confirm the human summary, upgrade guidance,
   changelog, safety boundary, and one technical-evidence section render.
2. Confirm the receipt, SPDX SBOM, and vulnerability report are attached.
3. Resolve the public GHCR tag and confirm its registry-reported digest matches
   the receipt.
4. Pull the immutable image digest and exercise `reefproof version` plus the
   affected packaged interface. For a Workbench change, start the image with a
   supported writable `/var/lib/reefproof` volume and fetch the real browser
   asset or API.
5. Report the tag, full source SHA, immutable image digest, workflow URLs,
   commands and results, untested boundaries, and whether deployment remains
   pending.

Deployment is a separate authorized action. Validate the exact digest on the
private-LAN LXC before calling the release deployment-accepted.

## 6. Correct existing release notes

Do not hand-edit the generated technical receipt or replace supply-chain assets.
To correct prose, changelog, warnings, or upgrade guidance:

1. Edit only `docs/releases/vX.Y.Z.md` and its release-contract tests.
2. Run focused release workflow tests and the proportional repository gate.
3. Commit and push the reviewed documentation change to `main` with explicit
   authority.
4. `.github/workflows/sync-release-notes.yml` downloads the existing immutable
   receipt, normalizes its technical-evidence section, and updates the matching
   GitHub Release through the repository-scoped workflow token.
5. Verify the live release body through GitHub, including exact heading counts,
   warnings, changelog links, and unchanged digest and evidence links.

The synchronizer skips a notes document when its matching GitHub Release does
not yet exist. New releases are created only by the tag workflow.
