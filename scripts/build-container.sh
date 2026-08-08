#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

container_tool="${CONTAINER_TOOL:-}"
if [[ -z "$container_tool" ]]; then
  if command -v podman >/dev/null 2>&1; then
    container_tool=podman
  elif command -v docker >/dev/null 2>&1; then
    container_tool=docker
  fi
fi
if [[ "$container_tool" != "podman" && "$container_tool" != "docker" ]]; then
  printf 'FAIL: CONTAINER_TOOL must resolve to podman or docker\n' >&2
  exit 1
fi
if ! command -v "$container_tool" >/dev/null 2>&1; then
  printf 'FAIL: container tool is unavailable: %s\n' "$container_tool" >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  printf '%s\n' 'FAIL: refusing to package a dirty working tree.' >&2
  exit 2
fi
if [[ ! -f dist/reefproof ]]; then
  printf 'FAIL: build binary first\n' >&2
  exit 1
fi

stage_root="$repository_root/.build/stage"
if [[ ! -f "$stage_root/Dockerfile" || ! -d "$stage_root/src" ]]; then
  uv run python scripts/build-stage.py --repo "$repository_root" --output "$stage_root"
fi

mkdir -p .build/container dist

source_url="${REEFPROOF_BUILD_SOURCE:-https://github.com/bobbravo2/ReefProof}"
revision="$(git rev-parse --verify HEAD)"
version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n1)"
created="$(git show -s --format=%cI HEAD)"
image_tag="reefproof:build-${revision:0:12}"
volume_name="reefproof-build-data-${revision:0:12}-$$"

cleanup() {
  "$container_tool" volume rm "$volume_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"$container_tool" build \
  --tag "$image_tag" \
  --build-arg SOURCE="$source_url" \
  --build-arg REVISION="$revision" \
  --build-arg VERSION="$version" \
  --build-arg CREATED="$created" \
  "$stage_root"

if [[ "$container_tool" == "podman" ]]; then
  "$container_tool" image inspect "$image_tag" --format json >.build/container/reefproof-image.json
else
  "$container_tool" image inspect "$image_tag" >.build/container/reefproof-image.json
fi
cp .build/container/reefproof-image.json dist/reefproof-image.json

run_read_only=(
  "$container_tool" run --rm --read-only --network=none --cap-drop=all
  --tmpfs /tmp:rw,noexec,nosuid,nodev
)
"${run_read_only[@]}" "$image_tag" version >/dev/null
"${run_read_only[@]}" "$image_tag" doctor >/dev/null

"$container_tool" volume create "$volume_name" >/dev/null
"${run_read_only[@]}" \
  --mount "source=$volume_name,target=/var/lib/reefproof" \
  "$image_tag" infra-smoke --format json >/dev/null

printf 'PASS: built and smoke-tested %s with %s\n' "$image_tag" "$container_tool"
