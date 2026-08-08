#!/usr/bin/env bash
set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
revision="$(git -C "$repository_root" rev-parse HEAD)"
build_root="$repository_root/.build"
runtime_root="$build_root/desktop-runtime"

mkdir -p "$build_root" "$runtime_root"
temporary_root="$(mktemp -d "$build_root/desktop-binary.XXXXXX")"
worktree="$temporary_root/source"

cleanup() {
  if git -C "$repository_root" worktree list --porcelain | grep -Fqx "worktree $worktree"; then
    git -C "$repository_root" worktree remove --force "$worktree"
  fi
  rm -rf "$temporary_root"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

git -C "$repository_root" worktree add --detach "$worktree" "$revision"
env UV_CACHE_DIR="$repository_root/.cache/uv" make -C "$worktree" build/binary

install -m 0755 "$worktree/dist/reefproof" "$runtime_root/reefproof"
printf '%s\n' "$revision" > "$runtime_root/revision"
printf 'PASS: staged desktop binary from Git revision %s\n' "$revision"
