"""Typed contracts for the local manual-model return-flow policy."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RETURN_FLOW_POLICY_TEMPLATE_ID = "RP-POLICY-FLOW-001"


class ReturnFlowPolicyTemplate(BaseModel):
    """Backend-authored field and provenance contract for the first journey."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    policy_template_id: Literal["RP-POLICY-FLOW-001"] = "RP-POLICY-FLOW-001"
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance: Literal["MANUAL"] = "MANUAL"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    units: Literal["gallons/hour"] = "gallons/hour"
    fields: tuple[str, ...] = (
        "tank_volume_gallons",
        "pump_rated_flow_gph",
        "delivered_flow_gph",
        "minimum_turnover_per_hour",
    )


class ReturnFlowPolicyInputs(BaseModel):
    """Operator-authored inputs; none are controller observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tank_volume_gallons: float = Field(gt=0, le=1_000_000)
    pump_rated_flow_gph: float = Field(gt=0, le=10_000_000)
    delivered_flow_gph: float = Field(gt=0, le=10_000_000)
    minimum_turnover_per_hour: float = Field(gt=0, le=1_000)


class ReturnFlowPolicyPreview(BaseModel):
    """Deterministic preview against an explicit operator-authored threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance: Literal["MANUAL"] = "MANUAL"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    policy_kind: Literal["operator-authored minimum turnover"] = (
        "operator-authored minimum turnover"
    )
    state: Literal["PASS", "FAIL"]
    tank_volume_gallons: float
    pump_rated_flow_gph: float
    delivered_flow_gph: float
    delivery_difference_gph: float
    delivery_efficiency_percent: float
    actual_turnover_per_hour: float
    minimum_turnover_per_hour: float
    minimum_delivered_flow_gph: float
    explanation: str


class ReturnFlowPolicyRevision(BaseModel):
    """One immutable, attributable local revision of the flow policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    revision_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    policy_template_id: Literal["RP-POLICY-FLOW-001"] = "RP-POLICY-FLOW-001"
    revision_number: int = Field(gt=0)
    created_at: datetime
    authoring_operator_session_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    collective_name: Literal["Mock Collective"] = "Mock Collective"
    provenance: Literal["MANUAL"] = "MANUAL"
    provenance_label: Literal["MANUAL / NOT LIVE"] = "MANUAL / NOT LIVE"
    live_observation: Literal[False] = False
    inputs: ReturnFlowPolicyInputs
    preview: ReturnFlowPolicyPreview

    @model_validator(mode="after")
    def created_at_must_be_aware(self) -> ReturnFlowPolicyRevision:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return self


def preview_flow(request: ReturnFlowPolicyInputs) -> ReturnFlowPolicyPreview:
    """Calculate authored flow evidence without implying a universal threshold."""

    actual_turnover = request.delivered_flow_gph / request.tank_volume_gallons
    minimum_flow = request.minimum_turnover_per_hour * request.tank_volume_gallons
    state: Literal["PASS", "FAIL"] = (
        "PASS" if actual_turnover >= request.minimum_turnover_per_hour else "FAIL"
    )
    comparison = "meets" if state == "PASS" else "does not meet"
    return ReturnFlowPolicyPreview(
        state=state,
        tank_volume_gallons=request.tank_volume_gallons,
        pump_rated_flow_gph=request.pump_rated_flow_gph,
        delivered_flow_gph=request.delivered_flow_gph,
        delivery_difference_gph=round(request.pump_rated_flow_gph - request.delivered_flow_gph, 3),
        delivery_efficiency_percent=round(
            request.delivered_flow_gph / request.pump_rated_flow_gph * 100, 3
        ),
        actual_turnover_per_hour=round(actual_turnover, 3),
        minimum_turnover_per_hour=request.minimum_turnover_per_hour,
        minimum_delivered_flow_gph=round(minimum_flow, 3),
        explanation=(
            f"The authored delivered flow {comparison} the operator-authored "
            "minimum turnover. This preview is manual evidence, not a live "
            "HYDROS observation or a universal safety recommendation."
        ),
    )
