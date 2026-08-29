#!/usr/bin/env python3
"""Verify the ReefProof build bundle metadata and checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_paths import resolve_under_root

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not SHA256_RE.fullmatch(parts[0]):
            raise ValueError(f"invalid checksum line {line_number}")
        digest, filename = parts[0], parts[1].strip()
        if filename in checksums:
            raise ValueError(f"duplicate checksum entry: {filename}")
        checksums[filename] = digest
    if not checksums:
        raise ValueError("checksum file is empty")
    return checksums


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("dist"))
    parser.add_argument("--checksums", type=Path, default=Path("SHA256SUMS"))
    parser.add_argument("--manifest", type=Path, default=Path("build-manifest.json"))
    parser.add_argument("--sbom", type=Path, default=Path("reefproof.spdx.json"))
    parser.add_argument("--image-receipt", type=Path, default=Path("reefproof-image.json"))
    parser.add_argument("--binary", type=Path, default=Path("reefproof"))
    parser.add_argument("--expected-display-identity", required=True)
    parser.add_argument("--expected-revision", required=True)
    arguments = parser.parse_args()

    root = arguments.root.resolve()
    checksum_path, checksum_relative = resolve_under_root(
        root, arguments.checksums, label="checksums"
    )
    manifest_path, manifest_relative = resolve_under_root(
        root, arguments.manifest, label="manifest"
    )
    sbom_path, sbom_relative = resolve_under_root(root, arguments.sbom, label="SBOM")
    image_receipt_path, image_relative = resolve_under_root(
        root, arguments.image_receipt, label="image receipt"
    )
    binary_path, binary_relative = resolve_under_root(root, arguments.binary, label="binary")

    required_paths = {
        checksum_path: "checksum file",
        manifest_path: "build manifest",
        sbom_path: "SPDX SBOM",
        image_receipt_path: "image receipt",
        binary_path: "binary artifact",
    }
    for path, label in required_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing {label}: {path}")

    expected_checksums = parse_checksums(checksum_path)
    resolved_checksums: dict[str, tuple[Path, str]] = {}
    for name, digest in expected_checksums.items():
        artifact_path, relative = resolve_under_root(root, Path(name), label="checksum artifact")
        relative_name = relative.as_posix()
        if relative_name != name:
            raise ValueError(f"checksum path is not normalized: {name}")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"missing artifact for checksum: {artifact_path}")
        actual = sha256(artifact_path)
        if actual != digest:
            raise ValueError(f"checksum mismatch for {name}")
        resolved_checksums[name] = (artifact_path, digest)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported build manifest schema")
    if manifest["product"]["display_identity"] != arguments.expected_display_identity:
        raise ValueError("display identity does not match expected candidate identity")
    if (
        manifest["product"]["display_identity"]
        != f"{manifest['product']['name']} {manifest['product']['version']}"
    ):
        raise ValueError("manifest display identity does not match product name and version")
    if manifest["source"]["revision"] != arguments.expected_revision:
        raise ValueError("source revision does not match expected candidate revision")

    manifest_artifacts = {entry["name"]: entry for entry in manifest["artifacts"]}
    if len(manifest_artifacts) != len(manifest["artifacts"]):
        raise ValueError("manifest contains duplicate artifact names")
    expected_manifest_names = set(expected_checksums) - {manifest_relative.as_posix()}
    if set(manifest_artifacts) != expected_manifest_names:
        raise ValueError("manifest artifact set does not match checksum artifact set")

    for name, entry in manifest_artifacts.items():
        artifact_path, digest = resolved_checksums[name]
        if entry.get("path") != name:
            raise ValueError(f"manifest path is not portable for {name}")
        if entry.get("sha256") != digest or entry.get("size") != artifact_path.stat().st_size:
            raise ValueError(f"manifest does not match artifact metadata for {name}")

    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if sbom.get("spdxVersion") != "SPDX-2.3":
        raise ValueError("SBOM is not SPDX 2.3")
    sbom_files = {entry["fileName"].removeprefix("./") for entry in sbom.get("files", [])}
    expected_sbom_files = set(manifest_artifacts) - {sbom_relative.as_posix()}
    if sbom_files != expected_sbom_files:
        raise ValueError("SBOM artifact set does not match manifest")

    receipt = json.loads(image_receipt_path.read_text(encoding="utf-8"))
    if isinstance(receipt, list):
        if len(receipt) != 1:
            raise ValueError("image receipt must contain exactly one image")
        receipt = receipt[0]
    config = receipt.get("Config", {})
    labels = config.get("Labels") or {}
    env = config.get("Env") or []
    if labels.get("org.opencontainers.image.title") != manifest["product"]["name"]:
        raise ValueError("container receipt title does not match manifest")
    if labels.get("org.opencontainers.image.version") != manifest["product"]["version"]:
        raise ValueError("container receipt version does not match manifest")
    if labels.get("org.opencontainers.image.revision") != manifest["source"]["revision"]:
        raise ValueError("container receipt revision does not match manifest")
    if labels.get("org.opencontainers.image.source") != manifest["source"]["url"]:
        raise ValueError("container receipt source does not match manifest")
    expected_data_directory = manifest["runtime"]["data_directory"]
    if f"REEFPROOF_DATA_DIRECTORY={expected_data_directory}" not in env:
        raise ValueError("container receipt missing data-directory contract")
    if config.get("Entrypoint") != [manifest["runtime"]["entrypoint"]]:
        raise ValueError("container receipt entrypoint does not match manifest")
    if str(config.get("User", "")).strip().lower() in {
        "",
        "0",
        "0:0",
        "root",
        "root:root",
    }:
        raise ValueError("container receipt configures a root user")
    if config.get("Cmd") != ["version"]:
        raise ValueError("container receipt default command is not one-shot version")

    for required in (
        binary_relative.as_posix(),
        image_relative.as_posix(),
        sbom_relative.as_posix(),
        manifest_relative.as_posix(),
    ):
        if required not in expected_checksums:
            raise ValueError(f"required artifact is not checksummed: {required}")
    archives = [name for name in expected_checksums if name.endswith(".tar.gz")]
    if len(archives) != 1:
        raise ValueError("bundle must contain exactly one checksummed binary archive")
    if checksum_relative.as_posix() in expected_checksums:
        raise ValueError("checksum file must not checksum itself")

    print(f"PASS: verified {len(expected_checksums)} checksum(s) and build metadata")


if __name__ == "__main__":
    main()
