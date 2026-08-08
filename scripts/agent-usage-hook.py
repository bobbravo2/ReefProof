#!/usr/bin/env python3.13
"""Repository-local Codex hook entry point with no third-party imports."""

from __future__ import annotations

import sys
from pathlib import Path

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root / "src"))

from reefproof.usage_hooks import hook_main  # noqa: E402

raise SystemExit(hook_main())
