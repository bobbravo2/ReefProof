"""Small, stable logging configuration for the product shell."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    *,
    log_level: str = "INFO",
    json_logs: bool = False,
    build_identity: str = "development",
) -> None:
    """Configure human console logs or newline-delimited JSON."""

    renderer: Any
    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    logging.basicConfig(format="%(message)s", level=log_level, stream=sys.stderr, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.EventRenamer("event_name"),
            structlog.processors.add_log_level,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(build_identity=build_identity)


def usage_event(event_name: str, **outcome_fields: object) -> None:
    """Log usage-ledger outcomes without conversational content."""

    structlog.get_logger().info(event_name, **outcome_fields)
