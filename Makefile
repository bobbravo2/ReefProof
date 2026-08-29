.DEFAULT_GOAL := help
.DELETE_ON_ERROR:

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
PYTEST_ARGS ?=
export UV_CACHE_DIR

PRODUCT_NAME := ReefProof
PRODUCT_VERSION := $(shell sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -n1)
DISPLAY_IDENTITY := $(PRODUCT_NAME) $(PRODUCT_VERSION)

SOURCE_URL := https://github.com/bobbravo2/ReefProof
SOURCE_REVISION := $(shell git rev-parse --verify HEAD 2>/dev/null || printf UNKNOWN)
BUILD_CREATED := $(shell git show -s --format=%cI HEAD 2>/dev/null || printf UNKNOWN)
BUILD_PLATFORM := $(shell uname -s | tr '[:upper:]' '[:lower:]')-$(shell uname -m)
CONTAINER_TOOL := $(shell if command -v podman >/dev/null 2>&1; then printf podman; elif command -v docker >/dev/null 2>&1; then printf docker; fi)
BUILD_IMAGE_TAG := reefproof:build-$(shell printf '%.12s' "$(SOURCE_REVISION)")

BUILD_ROOT := $(CURDIR)/.build
BUILD_STAGE_DIR := $(BUILD_ROOT)/stage
BUILD_STAMP_DIR := $(BUILD_ROOT)/stamps
BUILD_DIST_DIR := $(CURDIR)/dist

BUILD_STAGE_STAMP := $(BUILD_STAMP_DIR)/stage
BUILD_BINARY_STAMP := $(BUILD_STAMP_DIR)/binary
BUILD_HYDROS_PARITY_STAMP := $(BUILD_STAMP_DIR)/hydros-runtime-parity
BUILD_VERIFY_STAMP := $(BUILD_STAMP_DIR)/verified

BUILD_BINARY := $(BUILD_DIST_DIR)/reefproof
BINARY_ARCHIVE := $(BUILD_DIST_DIR)/reefproof-$(PRODUCT_VERSION)-$(BUILD_PLATFORM).tar.gz
BUILD_IMAGE_RECEIPT := $(BUILD_DIST_DIR)/reefproof-image.json
BUILD_SBOM := $(BUILD_DIST_DIR)/reefproof.spdx.json
BUILD_MANIFEST := $(BUILD_DIST_DIR)/build-manifest.json
BUILD_CHECKSUMS := $(BUILD_DIST_DIR)/SHA256SUMS

BUILD_SOURCE_FILES := $(shell git ls-files 2>/dev/null | while IFS= read -r path; do test -e "$$path" && printf '%s\n' "$$path"; done)

SETUP_TARGETS := setup setup/help setup/bootstrap
RUN_TARGETS := run run/help run/serve run/desktop run/desktop-app run/doctor run/snapshot run/graph run/check run/explain run/daemon-start run/daemon-stop run/daemon-status
TEST_TARGETS := test test/help test/format test/format-check test/lint test/typecheck test/frontend test/browser test/desktop test/python test/baseline test/api-contract test/check
BUILD_TARGETS := build build/help build/preflight build/clean build/desktop build/desktop-icons build/desktop-app build/stage build/binary build/container build/sbom build/checksums build/manifest build/verify build/delivery
OPS_TARGETS := ops ops/help ops/infra-smoke ops/database-backup ops/database-restore ops/database-verify
AGENT_TARGETS := agent agent/help agent/eval agent/benchmark agent/usage

.PHONY: \
	help \
	$(SETUP_TARGETS) \
	$(RUN_TARGETS) \
	$(TEST_TARGETS) \
	$(BUILD_TARGETS) \
	$(OPS_TARGETS) \
	$(AGENT_TARGETS)

help:
	@printf '%s\n' \
		'$(DISPLAY_IDENTITY) Make interface' \
		'' \
		'Primary workflows:' \
		'  make setup    Install local dependencies and tooling' \
		'  make run      Show the run domain helpers' \
		'  make test     Run the canonical test gate' \
		'  make check    Run the canonical complete quality gate' \
		'  make build    Produce a fresh verified distribution bundle' \
		'  make clean    Remove local build outputs' \
		'' \
		'Domains:' \
		'  make setup/help' \
		'  make run/help' \
		'  make test/help' \
		'  make build/help' \
		'  make ops/help' \
		'  make agent/help'

setup: setup/bootstrap
run: run/help
test: test/check
ops: ops/help
agent: agent/help
check: test/check
clean: build/clean

setup/help:
	@printf '%s\n' \
		'setup domain' \
		'  setup/bootstrap   Install local dependencies and tooling' \
		'' \
		'  make setup        Alias for setup/bootstrap'

setup/bootstrap:
	./scripts/bootstrap.sh

run/help:
	@printf '%s\n' \
		'run domain' \
		'  run/serve          Start the loopback workbench' \
		'  run/desktop        Start the workbench in Electron' \
		'  run/desktop-app    Open the packaged macOS application' \
		'  run/doctor         Check local development health' \
		'  run/snapshot       Render canonical snapshot evidence' \
		'  run/graph          Inspect reliability relationships' \
		'  run/check          Evaluate the bundled offline fixture' \
		'  run/explain        Explain one registered invariant' \
		'  run/daemon-start   Start the detached local daemon' \
		'  run/daemon-stop    Stop the detached local daemon' \
		'  run/daemon-status  Report detached daemon status' \
		'' \
		'  make run           Alias for run/help'

run/serve:
	./reefproof serve

run/desktop:
	npm run desktop:run

run/desktop-app:
	@test -d "dist/desktop/ReefProof-darwin-$$(node -p 'process.arch')/ReefProof.app" || { \
		printf '%s\n' 'FAIL: packaged desktop app is missing; run make build/desktop-app.' >&2; exit 2; \
	}
	open "dist/desktop/ReefProof-darwin-$$(node -p 'process.arch')/ReefProof.app"

run/doctor:
	./reefproof doctor

run/snapshot:
	./reefproof snapshot --fixture tests/fixtures/configuration/authored-minimal.json

run/graph:
	./reefproof graph --fixture tests/fixtures/configuration/unsafe-correlated-returns.json

run/check:
	./reefproof check --fixture tests/fixtures/configuration/safe-independent-returns.json

run/explain:
	./reefproof explain RP-CIRC-001

run/daemon-start:
	./reefproof daemon start

run/daemon-stop:
	./reefproof daemon stop

run/daemon-status:
	./reefproof daemon status

test/help:
	@printf '%s\n' \
		'test domain' \
		'  test/format        Format Python code' \
		'  test/format-check  Check Python formatting' \
		'  test/lint          Lint Python code' \
		'  test/typecheck     Run static type checks' \
		'  test/frontend      Run frontend checks' \
		'  test/browser       Run deterministic loopback Chromium tests' \
		'  test/desktop       Run focused Electron shell tests' \
		'  test/python        Run the Python test suite' \
		'  test/baseline      Run the repository baseline gate' \
		'  test/api-contract  Verify ADR 0008 routes against runtime and OpenAPI' \
		'  test/check         Run the full local quality gate' \
		'' \
		'Environment:' \
		'  PYTEST_ARGS        Additional pytest arguments (project default: -q -n 8)' \
		'' \
		'  make test          Alias for test/check' \
		'  make check         Alias for test/check'

test/format:
	uv run ruff format .

test/format-check:
	uv run ruff format --check .

test/lint:
	uv run ruff check .

test/typecheck:
	uv run pyright

test/frontend:
	npm run check
	npm test
	npm run desktop:test

test/browser:
	npm run test:browser

test/desktop:
	npm run desktop:test

test/python:
	uv run pytest $(PYTEST_ARGS)

test/baseline:
	./scripts/check-baseline.sh

test/api-contract:
	uv run pytest -q -n 0 tests/integration/test_api.py::test_openapi_describes_auth_and_groups_only_api_operations

test/check:
	./scripts/check-baseline.sh
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	npm run check
	npm test
	npm run test:browser
	npm run desktop:test
	uv run pytest $(PYTEST_ARGS)

build/help:
	@printf '%s\n' \
		'build domain' \
		'  build/preflight   Require a clean Git tree and common build tools' \
		'  build/desktop     Compile the Electron main process' \
		'  build/desktop-icons  Generate the native macOS icon' \
		'  build/desktop-app  Build the unsigned macOS application bundle' \
		'  build/clean       Remove .build and dist' \
		'  build/stage       Prepare the allowlisted staging tree' \
		'  build/binary      Build the standalone CLI artifact' \
		'  build/container   Build and smoke-test the OCI image' \
		'  build/sbom        Write the SPDX SBOM' \
		'  build/manifest    Write the build manifest' \
		'  build/checksums   Write SHA-256 checksums' \
		'  build/verify      Verify the distribution bundle' \
		'  build/delivery    Incrementally produce the verified bundle' \
		'' \
		'  make build        Clean, build, and verify the canonical bundle' \
		'  make clean        Remove local build outputs'

build/desktop:
	npm run desktop:build

build/desktop-icons:
	npm run desktop:icons

build/desktop-app:
	npm run desktop:package

build/preflight:
	@command -v git >/dev/null 2>&1 || { printf '%s\n' 'FAIL: git is required.' >&2; exit 2; }
	@command -v uv >/dev/null 2>&1 || { printf '%s\n' 'FAIL: uv is required.' >&2; exit 2; }
	@[[ "$(PRODUCT_VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$$ ]] || { \
		printf '%s\n' 'FAIL: project version must use numeric major.minor.patch.' >&2; \
		exit 2; \
	}
	@[[ "$(SOURCE_REVISION)" != "UNKNOWN" ]] || { printf '%s\n' 'FAIL: unable to resolve Git HEAD.' >&2; exit 2; }
	@[[ "$(BUILD_CREATED)" != "UNKNOWN" ]] || { printf '%s\n' 'FAIL: unable to resolve the Git commit timestamp.' >&2; exit 2; }
	@[[ -z "$$(git status --porcelain --untracked-files=normal)" ]] || { \
		printf '%s\n' 'FAIL: refusing to package a dirty working tree.' >&2; \
		exit 2; \
	}

build/clean:
	rm -rf "$(BUILD_ROOT)" "$(BUILD_DIST_DIR)"

build: build/preflight
	+$(MAKE) build/clean
	+$(MAKE) "$(BUILD_VERIFY_STAMP)"
	@printf '%s\n' "PASS: $(DISPLAY_IDENTITY) distribution bundle is ready in $(BUILD_DIST_DIR)/"

build/stage: build/preflight
	+$(MAKE) "$(BUILD_STAGE_STAMP)"

build/binary: build/preflight
	+$(MAKE) "$(BUILD_BINARY_STAMP)"
	@printf '%s\n' \
		'Next steps:' \
		'  Standalone binary:' \
		'  ./dist/reefproof version' \
		'  ./dist/reefproof doctor' \
		'  REEFPROOF_DATA_DIRECTORY=.local/infra-smoke ./dist/reefproof infra-smoke --format json'

build/container: build/preflight
	+$(MAKE) "$(BUILD_IMAGE_RECEIPT)"
	@printf '%s\n' \
		'Next steps:' \
		'  OCI image (runtime: $(CONTAINER_TOOL)):' \
		'  $(CONTAINER_TOOL) run --rm --read-only --network=none --cap-drop=all --tmpfs /tmp:rw,noexec,nosuid,nodev $(BUILD_IMAGE_TAG) version' \
		'  $(CONTAINER_TOOL) run --rm --read-only --network=none --cap-drop=all --tmpfs /tmp:rw,noexec,nosuid,nodev $(BUILD_IMAGE_TAG) doctor' \
		'  $(CONTAINER_TOOL) run --rm --read-only --network=none --cap-drop=all --tmpfs /tmp:rw,noexec,nosuid,nodev $(BUILD_IMAGE_TAG) infra-smoke --format json'

build/sbom: build/preflight
	+$(MAKE) "$(BUILD_SBOM)"

build/manifest: build/preflight
	+$(MAKE) "$(BUILD_MANIFEST)"

build/checksums: build/preflight
	+$(MAKE) "$(BUILD_CHECKSUMS)"

build/verify: build/preflight
	+$(MAKE) "$(BUILD_VERIFY_STAMP)"

build/delivery: build/preflight
	+$(MAKE) "$(BUILD_VERIFY_STAMP)"
	@printf '%s\n' "PASS: $(DISPLAY_IDENTITY) distribution bundle is ready in $(BUILD_DIST_DIR)/"

$(BUILD_STAGE_DIR) $(BUILD_STAMP_DIR) $(BUILD_DIST_DIR):
	mkdir -p "$@"

$(BUILD_STAGE_STAMP): $(BUILD_SOURCE_FILES) | $(BUILD_STAGE_DIR) $(BUILD_STAMP_DIR)
	uv run python scripts/build-stage.py --repo . --output "$(BUILD_STAGE_DIR)"
	touch "$@"

$(BUILD_BINARY_STAMP): $(BUILD_STAGE_STAMP) scripts/build-binary.sh | $(BUILD_DIST_DIR) $(BUILD_STAMP_DIR)
	./scripts/build-binary.sh
	test -x "$(BUILD_BINARY)"
	test -f "$(BINARY_ARCHIVE)"
	touch "$@"

$(BUILD_IMAGE_RECEIPT): $(BUILD_BINARY_STAMP) scripts/build-container.sh | $(BUILD_DIST_DIR)
	@if [[ -z "$(CONTAINER_TOOL)" ]]; then \
		printf '%s\n' 'FAIL: podman or docker is required for build/container.' >&2; \
		exit 2; \
	fi
	CONTAINER_TOOL="$(CONTAINER_TOOL)" ./scripts/build-container.sh
	test -f "$@"

$(BUILD_SBOM): $(BUILD_BINARY_STAMP) $(BUILD_IMAGE_RECEIPT) scripts/build-sbom.py | $(BUILD_DIST_DIR)
	uv run python scripts/build-sbom.py \
		--output "$@" \
		--product-name "$(PRODUCT_NAME)" \
		--version "$(PRODUCT_VERSION)" \
		--revision "$(SOURCE_REVISION)" \
		--source "$(SOURCE_URL)" \
		--created "$(BUILD_CREATED)" \
		--root "$(BUILD_DIST_DIR)" \
		"$(notdir $(BUILD_BINARY))" \
		"$(notdir $(BINARY_ARCHIVE))" \
		"$(notdir $(BUILD_IMAGE_RECEIPT))"

$(BUILD_MANIFEST): $(BUILD_SBOM) scripts/build-manifest.py | $(BUILD_DIST_DIR)
	uv run python scripts/build-manifest.py \
		--output "$@" \
		--product-name "$(PRODUCT_NAME)" \
		--version "$(PRODUCT_VERSION)" \
		--display-identity "$(DISPLAY_IDENTITY)" \
		--revision "$(SOURCE_REVISION)" \
		--source "$(SOURCE_URL)" \
		--created "$(BUILD_CREATED)" \
		--entrypoint reefproof \
		--data-directory /var/lib/reefproof \
		--root "$(BUILD_DIST_DIR)" \
		"$(notdir $(BUILD_BINARY))" \
		"$(notdir $(BINARY_ARCHIVE))" \
		"$(notdir $(BUILD_IMAGE_RECEIPT))" \
		"$(notdir $(BUILD_SBOM))"

$(BUILD_CHECKSUMS): $(BUILD_MANIFEST) scripts/build-checksums.py | $(BUILD_DIST_DIR)
	uv run python scripts/build-checksums.py \
		--root "$(BUILD_DIST_DIR)" \
		--output "$@" \
		"$(notdir $(BUILD_BINARY))" \
		"$(notdir $(BINARY_ARCHIVE))" \
		"$(notdir $(BUILD_IMAGE_RECEIPT))" \
		"$(notdir $(BUILD_SBOM))" \
		"$(notdir $(BUILD_MANIFEST))"

$(BUILD_HYDROS_PARITY_STAMP): $(BUILD_IMAGE_RECEIPT) scripts/verify-hydros-runtimes.py tests/fixtures/configuration/hydros-download-config-sanitized.json | $(BUILD_STAMP_DIR)
	uv run python scripts/verify-hydros-runtimes.py \
		--source-cli "$(CURDIR)/reefproof" \
		--binary "$(BUILD_BINARY)" \
		--container-tool "$(CONTAINER_TOOL)" \
		--image "$(BUILD_IMAGE_TAG)" \
		--hydros-export tests/fixtures/configuration/hydros-download-config-sanitized.json \
		--captured-at 2026-07-31T19:45:00-04:00 \
		--expected-temperature-unit fahrenheit
	touch "$@"

$(BUILD_VERIFY_STAMP): $(BUILD_CHECKSUMS) $(BUILD_HYDROS_PARITY_STAMP) scripts/build-verify.py | $(BUILD_STAMP_DIR)
	uv run python scripts/build-verify.py \
		--root "$(BUILD_DIST_DIR)" \
		--checksums "$(BUILD_CHECKSUMS)" \
		--manifest "$(BUILD_MANIFEST)" \
		--sbom "$(BUILD_SBOM)" \
		--image-receipt "$(BUILD_IMAGE_RECEIPT)" \
		--binary "$(BUILD_BINARY)" \
		--expected-display-identity "$(DISPLAY_IDENTITY)" \
		--expected-revision "$(SOURCE_REVISION)"
	touch "$@"

ops/help:
	@printf '%s\n' \
		'ops domain' \
		'  ops/infra-smoke     Run the network-free evidence-store scenario' \
		'  ops/database-backup  Create a SQLite-consistent backup' \
		'  ops/database-restore Restore a SQLite backup to a new target' \
		'  ops/database-verify  Check SQLite integrity' \
		'' \
		'  make ops            Alias for ops/help'

ops/infra-smoke:
	REEFPROOF_DATA_DIRECTORY=.local/infra-smoke ./reefproof infra-smoke --format json

ops/database-backup:
	./reefproof database backup .local/backups/reefproof.sqlite3

ops/database-restore:
	./reefproof database restore .local/backups/reefproof.sqlite3 .local/restores/reefproof.sqlite3

ops/database-verify:
	REEFPROOF_DATA_DIRECTORY=.local/infra-smoke ./reefproof database verify

agent/help:
	@printf '%s\n' \
		'agent domain' \
		'  agent/eval   Authenticated, networked, token-consuming Codex evaluation' \
		'  agent/usage  Print optional local agent-usage telemetry' \
		'' \
		'Agent evaluations are explicit and are not part of make check.'

agent/eval:
	./scripts/1-shot-eval-benchmark.sh

agent/usage:
	./scripts/agent-usage.sh summary
