"""Explicit invariant registry."""

from __future__ import annotations

from typing import Protocol

from reefproof.invariants.circulation import (
    LowPowerCirculationRule,
    RedundantReturnsPowerDomainRule,
    SurvivingCirculationPathRule,
)
from reefproof.invariants.fallback import CriticalOutputFallbackRule
from reefproof.invariants.flow import ChillerFlowPermissiveRule, UvFlowPermissiveRule
from reefproof.invariants.heaters import (
    IndependentHeaterSafeguardRule,
    RedundantHeaterFailureDomainRule,
)
from reefproof.invariants.logic import DependencyCycleRule
from reefproof.invariants.models import Severity
from reefproof.invariants.modes import FiniteServiceModeTimeoutRule
from reefproof.invariants.monitor import MONITOR_RULES
from reefproof.invariants.protocol import InvariantRule
from reefproof.invariants.water import BoundedAtoAdditionRule, IndependentRodiHighHighRule


class InvariantDefinition(Protocol):
    invariant_id: str
    version: str
    severity: Severity
    title: str

    def explain(self) -> str: ...


def registered_invariant_definitions() -> tuple[InvariantDefinition, ...]:
    """Return the exact executable v0.1 invariant catalog."""

    return (*registered_rules(), *MONITOR_RULES)


def registered_rules() -> tuple[InvariantRule, ...]:
    return (
        RedundantReturnsPowerDomainRule(),
        SurvivingCirculationPathRule(),
        LowPowerCirculationRule(),
        CriticalOutputFallbackRule(),
        UvFlowPermissiveRule(),
        ChillerFlowPermissiveRule(),
        RedundantHeaterFailureDomainRule(),
        IndependentHeaterSafeguardRule(),
        DependencyCycleRule(),
        FiniteServiceModeTimeoutRule(),
        BoundedAtoAdditionRule(),
        IndependentRodiHighHighRule(),
    )


def registered_invariant_ids() -> frozenset[str]:
    """Return the bounded built-in metric-label allowlist."""

    return frozenset(rule.invariant_id for rule in registered_invariant_definitions())


def explain_invariant(invariant_id: str) -> str:
    for rule in registered_invariant_definitions():
        if rule.invariant_id == invariant_id:
            return rule.explain()
    raise KeyError(f"unknown invariant: {invariant_id}")
