#!/usr/bin/env python3
"""Write an SPDX 2.3 document for the ReefProof distribution artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    parser.add_argument("--output", type=Path, default=Path("dist/reefproof.spdx.json"))
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--root", type=Path, default=Path("dist"))
    parser.add_argument("artifacts", nargs="+", type=Path)
    arguments = parser.parse_args()

    root = arguments.root.resolve()
    output = resolve_output(arguments.output)
    files = []
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-ReefProof",
        }
    ]
    seen: set[str] = set()
    for index, artifact in enumerate(arguments.artifacts, start=1):
        artifact_path, relative = resolve_under_root(root, artifact, label="artifact")
        relative_name = relative.as_posix()
        if relative_name in seen:
            parser.error(f"duplicate artifact: {relative_name}")
        seen.add(relative_name)
        if not artifact_path.is_file():
            raise FileNotFoundError(f"missing artifact: {artifact_path}")
        spdx_id = f"SPDXRef-File-{index}"
        files.append(
            {
                "SPDXID": spdx_id,
                "checksums": [{"algorithm": "SHA256", "checksumValue": sha256(artifact_path)}],
                "copyrightText": "NOASSERTION",
                "fileName": f"./{relative_name}",
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-ReefProof",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": spdx_id,
            }
        )

    document = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": arguments.created,
            "creators": [f"Tool: {arguments.product_name} build"],
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": f"{arguments.source.rstrip('/')}/spdx/"
        f"{arguments.revision}/{arguments.version}",
        "files": files,
        "name": f"{arguments.product_name} {arguments.version} build SBOM",
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-ReefProof",
                "copyrightText": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": arguments.product_name,
                "versionInfo": arguments.version,
            }
        ],
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS: wrote SPDX SBOM to {output}")


if __name__ == "__main__":
    main()
