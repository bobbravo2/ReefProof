#!/usr/bin/env python3
"""Fail closed unless a release tag matches ReefProof's package version."""

from __future__ import annotations

import argparse

from reefproof import __version__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Exact Git tag proposed for publication.")
    arguments = parser.parse_args()

    expected = f"v{__version__}"
    if arguments.tag != expected:
        parser.error(f"release tag {arguments.tag!r} does not match package version {expected!r}")
    print(f"PASS: release tag {arguments.tag} matches package version {__version__}")


if __name__ == "__main__":
    main()
