"""Narrow alert policy and adapter boundaries."""

from reefproof.alerting.console import ConsoleAlertAdapter
from reefproof.alerting.coordinator import (
    AlertCoordinator,
    DeliveryResult,
    DeliveryStatus,
)
from reefproof.alerting.home_assistant import HomeAssistantAlertAdapter
from reefproof.alerting.policy import AlertAction, AlertDecision, AlertPolicy
from reefproof.alerting.protocol import AlertAdapter, AlertEvent

__all__ = [
    "AlertAction",
    "AlertAdapter",
    "AlertCoordinator",
    "AlertDecision",
    "AlertEvent",
    "AlertPolicy",
    "ConsoleAlertAdapter",
    "DeliveryResult",
    "DeliveryStatus",
    "HomeAssistantAlertAdapter",
]
