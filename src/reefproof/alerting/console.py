"""Console alert adapter for offline development."""

from __future__ import annotations

import json
import sys
from typing import TextIO

from reefproof.alerting.protocol import AlertEvent


class ConsoleAlertAdapter:
    name = "console"

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    async def send(self, event: AlertEvent) -> None:
        document = event.model_dump(mode="json")
        self._stream.write(f"{json.dumps(document, ensure_ascii=False, sort_keys=True)}\n")
        self._stream.flush()
