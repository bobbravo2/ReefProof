"""Application orchestration without transport control capability."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reefproof.service.health import AssuranceReadiness as AssuranceReadiness
    from reefproof.service.health import MonitoringConfidence as MonitoringConfidence
    from reefproof.service.health import ReadinessReport as ReadinessReport
    from reefproof.service.health import RuntimeState as RuntimeState
    from reefproof.service.health import evaluate_readiness as evaluate_readiness
    from reefproof.service.hydros_import import HydrosImportRun as HydrosImportRun
    from reefproof.service.hydros_import import import_hydros_export as import_hydros_export
    from reefproof.service.pipeline import (
        FixtureEvaluationPipeline as FixtureEvaluationPipeline,
    )
    from reefproof.service.pipeline import PipelineRun as PipelineRun
    from reefproof.service.state import RuntimeStateStore as RuntimeStateStore

__all__ = [
    "AssuranceReadiness",
    "FixtureEvaluationPipeline",
    "HydrosImportRun",
    "MonitoringConfidence",
    "PipelineRun",
    "ReadinessReport",
    "RuntimeState",
    "RuntimeStateStore",
    "evaluate_readiness",
    "import_hydros_export",
]

_EXPORTS = {
    "AssuranceReadiness": ("reefproof.service.health", "AssuranceReadiness"),
    "MonitoringConfidence": ("reefproof.service.health", "MonitoringConfidence"),
    "ReadinessReport": ("reefproof.service.health", "ReadinessReport"),
    "RuntimeState": ("reefproof.service.health", "RuntimeState"),
    "evaluate_readiness": ("reefproof.service.health", "evaluate_readiness"),
    "HydrosImportRun": ("reefproof.service.hydros_import", "HydrosImportRun"),
    "import_hydros_export": ("reefproof.service.hydros_import", "import_hydros_export"),
    "FixtureEvaluationPipeline": (
        "reefproof.service.pipeline",
        "FixtureEvaluationPipeline",
    ),
    "PipelineRun": ("reefproof.service.pipeline", "PipelineRun"),
    "RuntimeStateStore": ("reefproof.service.state", "RuntimeStateStore"),
}


def __getattr__(name: str):
    binding = _EXPORTS.get(name)
    if binding is None:
        raise AttributeError(name)
    module_name, attribute_name = binding
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
