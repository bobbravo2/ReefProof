#!/usr/bin/env python3
"""Write deterministic SHA-256 checksums for build artifacts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from build_paths import resolve_output, resolve_under_root


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("dist/SHA256SUMS"))
    parser.add_argument("artifacts", nargs="+", type=Path)
    arguments = parser.parse_args()

    root = arguments.root.resolve()
    output = resolve_output(arguments.output)
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for artifact in arguments.artifacts:
        artifact_path, relative = resolve_under_root(root, artifact, label="artifact")
        relative_name = relative.as_posix()
        if relative_name in seen:
            parser.error(f"duplicate artifact: {relative_name}")
        seen.add(relative_name)
        if not artifact_path.is_file():
            raise FileNotFoundError(f"missing artifact: {artifact_path}")
        entries.append((relative_name, sha256(artifact_path)))

    entries.sort(key=lambda item: item[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in entries),
        encoding="utf-8",
    )
    print(f"PASS: wrote {len(entries)} checksum(s) to {output}")


if __name__ == "__main__":
    main()
