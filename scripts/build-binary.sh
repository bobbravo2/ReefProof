#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$repository_root/.cache/uv}"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$repository_root/.build/pyinstaller/config}"

stage_root="$repository_root/.build/stage"
pyinstaller_root="$repository_root/.build/pyinstaller"
dist_root="$repository_root/dist"
migration_root="$stage_root/src/reefproof/storage/migrations"
revision="$(git rev-parse --verify HEAD)"
created="$(git show -s --format=%cI HEAD)"
source="${REEFPROOF_BUILD_SOURCE:-https://github.com/bobbravo2/ReefProof}"
version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n1)"
platform_name="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
binary_archive="$dist_root/reefproof-$version-$platform_name.tar.gz"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  printf '%s\n' 'FAIL: refusing to package a dirty working tree.' >&2
  exit 2
fi
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'FAIL: invalid project version: %s\n' "$version" >&2
  exit 2
fi

if [[ ! -f "$stage_root/pyproject.toml" || ! -d "$stage_root/src" ]]; then
  uv run python scripts/build-stage.py --repo "$repository_root" --output "$stage_root"
fi

if [[ ! -f "$migration_root/env.py" ]]; then
  printf 'FAIL: missing staged alembitmigration environment: %s\n' \
    "$migration_root/env.py" >&2
  exit 2
fi

mkdir -p "$pyinstaller_root" "$dist_root"

uv run python scripts/write-build-identity.py \
  --output "$stage_root/src/reefproof/_build_identity.py" \
  --revision "$revision" \
  --source "$source" \
  --created "$created"

uv sync \
  --project "$stage_root" \
  --locked \
  --no-dev \
  --group build \
  --no-editable

pyinstaller_args=(
  --clean \
  --distpath "$dist_root" \
  --specpath "$pyinstaller_root/spec" \
  --workpath "$pyinstaller_root/work" \
  --name reefproof \
  --onefile \
  --paths "$stage_root/src" \
  --collect-data reefproof \
  --collect-submodules reefproof \
  --add-data "$migration_root:reefproof/storage/migrations" \
  --exclude-module _pytest \
  --exclude-module pytest \
  --exclude-module pyright \
  --exclude-module ruff \
  --exclude-module setuptools \
  "$stage_root/src/reefproof/__main__.py"
)

# urllib.request imports Apple's proxy helper on macOS. PyInstaller does not
# reliably discover this optional stdlib extension through httpx's import path.
if [[ "$(uname -s)" == "Darwin" ]]; then
  pyinstaller_args+=(--hidden-import _scproxy)
fi

"$stage_root/.venv/bin/pyinstaller" "${pyinstaller_args[@]}"

PYI_ARCHIVE_VIEWER="$stage_root/.venv/bin/pyi-archive_viewer" \
  ./scripts/verify-binary.sh "$dist_root/reefproof" "$revision"

tar -C "$dist_root" -czf "$binary_archive" reefproof

printf 'PASS: created binary archive: %s\n' "$binary_archive"
