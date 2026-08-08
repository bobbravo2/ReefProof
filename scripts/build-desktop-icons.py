#!/usr/bin/env python3
"""Generate the native macOS icon from the checked-in ReefProof desktop PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def main() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    source = repository_root / "desktop" / "assets" / "icon.png"
    output = repository_root / "desktop" / "assets" / "icon.icns"
    with Image.open(source) as icon:
        if icon.width != icon.height:
            raise ValueError(
                f"desktop icon must be square to preserve its proportions: "
                f"{source} is {icon.width}x{icon.height}"
            )
        icon.save(
            output,
            format="ICNS",
            sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
        )
    print(f"PASS: generated macOS desktop icon: {output}")


if __name__ == "__main__":
    main()
