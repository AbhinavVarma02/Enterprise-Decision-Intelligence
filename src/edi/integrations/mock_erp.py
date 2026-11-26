"""Mock ERP adapter: purchase requisition JSON in, decision candidate and validation report out, and a
simulated purchase order for approved decisions. Nothing is sent to any external system.

The requisition format is invented for this demo (loosely shaped like a planning-system export). It is
not SAP, Oracle or any vendor's real interface.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from edi.validation.engine import ValidatorParams, validate
from edi.validation.inventory import RESOURCES, InventoryAdapter
from edi.validation.schema import (
    AuthoritativeContext,
    Constraints,
    DataSnapshot,
    DecisionCandidate,
    Entity,
    FinancialAssumptions,
    ForecastDistribution,
    Objective,
    Resource,
    ScenarioResults,
    ValidationReport,
)

MAX_LINES = 10


class RequisitionLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_id: str = Field(pattern=r"^[A-Z0-9\-]{2,20}$")
    quantity: float = Field(ge=0, lt=1e7)
    unit_price: float = Field(gt=0, lt=1e6)
    delivery_days: int = Field(ge=0, le=3)


class VendorTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_id: str
    role: str = Field(pattern="^(primary|alternate|expedite)$")
    unit_price: float = Field(gt=0)
    delivery_days: int = Field(ge=0, le=3)
    capacity: float = Field(ge=0)
    min_order_qty: float = Field(default=0.0, ge=0)
    approved: bool = True
    active: bool = True


class PurchaseRequisition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requisition_id: str = Field(pattern=r"^[A-Za-z0-9\-_.]{1,60}$")
    plant: str = Field(max_length=40)
    material: str = Field(max_length=60)
    category: str = Field(max_length=40)
    created_at: str
    snapshot_age_hours: float = Field(ge=0)
    typical_daily_demand: float = Field(gt=0)
    on_hand_by_age: list[float] = Field(min_length=1, max_length=60)
    inbound_by_day: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0], max_length=8)
    lines: list[RequisitionLine] = Field(min_length=1, max_length=MAX_LINES)
    vendors_as_planned: list[VendorTerms] = Field(min_length=1, max_length=8)
    budget: float = Field(ge=0)
    forecast_levels: list[float]
    forecast_quantiles: list[list[float]]
    claimed_expected_cost: float | None = None
    economics: FinancialAssumptions
    source_system: str = "mock-erp"


def requisition_to_candidate(req: PurchaseRequisition) -> DecisionCandidate:
    by_vendor = {v.vendor_id: v for v in req.vendors_as_planned}
    role_terms = {v.role: v for v in req.vendors_as_planned}
    action = {r: 0.0 for r in RESOURCES}
    for line in req.lines:
        v = by_vendor.get(line.vendor_id)
        if v is None:
            raise ValueError(f"vendor {line.vendor_id} is not in the planning vendor list")
        action[v.role] += line.quantity
    resources = []
    for role in RESOURCES:
        v = role_terms.get(role)
        if v is None:
            resources.append(Resource(name=role, lead_days=0, unit_cost=1.0, capacity=0.0, available=False))
        else:
            resources.append(
                Resource(
                    name=role,
                    lead_days=v.delivery_days,
                    unit_cost=v.unit_price,
                    capacity=v.capacity,
                    min_quantity=v.min_order_qty,
                    eligible=v.approved,
                    available=v.active,
                    attributes={"vendor_id": v.vendor_id},
                )
            )
    return DecisionCandidate(
        decision_id=f"erp.{req.requisition_id}",
        domain="inventory_replenishment",
        decision_day=0,
        decision_time=req.created_at,
        entity=Entity(
            entity_id=f"{req.plant}:{req.material}",
            label=req.material,
            category=req.category,
            typical_daily_volume=req.typical_daily_demand,
        ),
        data_snapshot=DataSnapshot(
            snapshot_id=f"{req.source_system}:{req.requisition_id}",
            as_of=req.created_at,
            age_hours=req.snapshot_age_hours,
            state={"on_hand_by_age": req.on_hand_by_age, "pipeline_by_day": req.inbound_by_day},
        ),
        action=action,
        objective=Objective(type="external"),
        constraints=Constraints(resources=resources, budget=req.budget),
        forecast=ForecastDistribution(
            model_version=f"{req.source_system}-forecast",
            levels=req.forecast_levels,
            quantiles=req.forecast_quantiles,
        ),
        financial_assumptions=req.economics,
        scenario_results=ScenarioResults(expected_cost=req.claimed_expected_cost, n_scenarios=0)
        if req.claimed_expected_cost is not None
        else None,
        model_version=f"{req.source_system}-forecast",
        policy_version=f"{req.source_system}-mrp",
    )


def validate_requisition(
    req_payload: dict[str, Any], context_payload: dict[str, Any], params: ValidatorParams | None = None
) -> tuple[DecisionCandidate, ValidationReport]:
    req = PurchaseRequisition.model_validate(req_payload)
    ctx = AuthoritativeContext.model_validate(context_payload)
    cand = requisition_to_candidate(req)
    return cand, validate(cand, ctx, InventoryAdapter(), params or ValidatorParams())


def to_purchase_order(
    req_payload: dict[str, Any], report: ValidationReport, approved_by: str | None = None
) -> dict[str, Any]:
    """Simulated PO for a recommended (or explicitly approved) requisition. Never transmitted anywhere."""
    if report.outcome != "recommend" and not approved_by:
        raise PermissionError(f"requisition outcome is '{report.outcome}'; a named approver is required")
    req = PurchaseRequisition.model_validate(req_payload)
    return {
        "simulated": True,
        "purchase_order_id": f"SIM-PO-{req.requisition_id}",
        "requisition_id": req.requisition_id,
        "lines": [line.model_dump() for line in req.lines if line.quantity > 0],
        "validation_outcome": report.outcome,
        "approved_by": approved_by or "auto (validation recommend)",
        "note": "Simulated document for demonstration. No external system was contacted.",
    }
