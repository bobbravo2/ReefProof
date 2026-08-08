#!/usr/bin/env python3
"""Write the versioned build manifest for the ReefProof distribution bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_paths import resolve_output, resolve_under_root

SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist/build-manifest.json"))
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--display-identity", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--data-directory", required=True)
    parser.add_argument("--root", type=Path, default=Path("dist"))
    parser.add_argument("artifacts", nargs="+", type=Path)
    arguments = parser.parse_args()

    if not SEMVER.fullmatch(arguments.version):
        parser.error("version must use numeric major.minor.patch")
    expected_identity = f"{arguments.product_name} {arguments.version}"
    if arguments.display_identity != expected_identity:
        parser.error(f"display identity must be {expected_identity!r}")

    root = arguments.root.resolve()
    output = resolve_output(arguments.output)
    artifacts = []
    seen: set[str] = set()
    for artifact in arguments.artifacts:
        artifact_path, relative = resolve_under_root(root, artifact, label="artifact")
        relative_name = relative.as_posix()
        if relative_name in seen:
            parser.error(f"duplicate artifact: {relative_name}")
        seen.add(relative_name)
        if not artifact_path.is_file():
            raise FileNotFoundError(f"missing artifact: {artifact_path}")
        artifacts.append(
            {
                "name": relative_name,
                "path": relative_name,
                "sha256": sha256(artifact_path),
                "size": artifact_path.stat().st_size,
            }
        )

    artifacts.sort(key=lambda entry: entry["name"])
    document = {
        "schema_version": 1,
        "artifacts": artifacts,
        "product": {
            "display_identity": arguments.display_identity,
            "name": arguments.product_name,
            "version": arguments.version,
        },
        "runtime": {
            "data_directory": arguments.data_directory,
            "entrypoint": arguments.entrypoint,
        },
        "source": {
            "created": arguments.created,
            "revision": arguments.revision,
            "url": arguments.source,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS: wrote build manifest to {output}")


if __name__ == "__main__":
    main()
