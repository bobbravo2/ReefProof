#!/usr/bin/env python3
"""Write a small Python build-identity module without reading host secrets."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--created", required=True)
    arguments = parser.parse_args()

    values = {
        "BUILD_CREATED": arguments.created,
        "BUILD_REVISION": arguments.revision,
        "BUILD_SOURCE": arguments.source,
    }
    document = '"""Generated immutable build identity. Do not edit."""\n\n'
    document += "".join(f"{name} = {value!r}\n" for name, value in values.items())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
