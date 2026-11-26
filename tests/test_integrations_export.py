"""Mock ERP adapter, JSON schemas and the studio reference used for browser parity."""

from __future__ import annotations

import json

import numpy as np
import pytest
from pydantic import ValidationError

from edi.integrations.mock_erp import (
    PurchaseRequisition,
    requisition_to_candidate,
    to_purchase_order,
    validate_requisition,
)
from edi.validation.engine import ValidatorParams

LEVELS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]


def requisition(**over):
    base = {
        "requisition_id": "PR-1001",
        "plant": "S03",
        "material": "P10012",
        "category": "fruit",
        "created_at": "2024-06-26T06:00",
        "snapshot_age_hours": 20,
        "typical_daily_demand": 20.0,
        "on_hand_by_age": [6.0, 3.0, 0.0, 0.0],
        "inbound_by_day": [0, 0, 0, 0],
        "lines": [{"vendor_id": "V-100", "quantity": 18.0, "unit_price": 2.7, "delivery_days": 1}],
        "vendors_as_planned": [
            {
                "vendor_id": "V-100",
                "role": "primary",
                "unit_price": 2.7,
                "delivery_days": 1,
                "capacity": 50,
                "min_order_qty": 8,
            },
            {
                "vendor_id": "V-200",
                "role": "alternate",
                "unit_price": 3.02,
                "delivery_days": 1,
                "capacity": 24,
            },
            {
                "vendor_id": "V-900",
                "role": "expedite",
                "unit_price": 3.65,
                "delivery_days": 0,
                "capacity": 12,
            },
        ],
        "budget": 162.0,
        "forecast_levels": LEVELS,
        "forecast_quantiles": [[11, 13, 16.4, 20, 23.6, 27.6, 30.4]] * 2,
        "claimed_expected_cost": None,
        "economics": {
            "price": 4.5,
            "unit_cost": 2.7,
            "holding": 0.05,
            "disposal": 0.1,
            "goodwill": 0.6,
            "shelf_life_days": 4,
            "terminal_waste_risk": 0.25,
        },
    }
    base.update(over)
    return base


def context(**over):
    req = PurchaseRequisition.model_validate(requisition())
    cand = requisition_to_candidate(req)
    ctx = {
        "constraints": cand.constraints.model_dump(),
        "financial_assumptions": cand.financial_assumptions.model_dump(),
        "approval_threshold": 130.0,
        "max_share": {"expedite": 0.6},
        "freshness_max_age_hours": 30,
        "signals": {},
        "investigation_cost": 2.7,
        "review_cost": 5.4,
    }
    ctx.update(over)
    return ctx


def test_requisition_maps_to_candidate_and_validates() -> None:
    cand, rep = validate_requisition(requisition(), context(), ValidatorParams(n_scenarios=60))
    assert cand.action["primary"] == 18.0 and cand.decision_id == "erp.PR-1001"
    assert rep.outcome in ("recommend", "escalate")
    assert len(rep.gates) == 7


def test_unapproved_vendor_requisition_is_rejected_and_no_po_is_issued() -> None:
    ctx = context()
    ctx["constraints"]["resources"][1]["eligible"] = False
    req = requisition(
        lines=[{"vendor_id": "V-200", "quantity": 10.0, "unit_price": 3.02, "delivery_days": 1}]
    )
    _, rep = validate_requisition(req, ctx, ValidatorParams(n_scenarios=60))
    assert rep.outcome == "reject"
    with pytest.raises(PermissionError):
        to_purchase_order(req, rep)
    po = to_purchase_order(req, rep, approved_by="planner@example.test")
    assert po["simulated"] is True


def test_requisition_input_is_bounded() -> None:
    with pytest.raises(ValidationError):
        PurchaseRequisition.model_validate(requisition(requisition_id="../../etc/passwd"))
    with pytest.raises(ValidationError):
        PurchaseRequisition.model_validate(requisition(lines=[]))
    with pytest.raises(ValueError):
        requisition_to_candidate(
            PurchaseRequisition.model_validate(
                requisition(
                    lines=[{"vendor_id": "V-777", "quantity": 1.0, "unit_price": 1.0, "delivery_days": 1}]
                )
            )
        )


def test_schemas_are_written_and_parse(tmp_path, monkeypatch) -> None:
    from edi.export import web

    paths = web.write_schemas()
    for p in paths:
        schema = json.loads(p.read_text())
        assert "properties" in schema


def test_studio_reference_is_consistent_with_grid_search() -> None:
    from edi.export.web import studio_evaluate

    q = [[11, 13, 16.4, 20, 23.6, 27.6, 30.4]] * 3
    rng = np.random.default_rng(3)
    case = {
        "id": "t",
        "day": 91,
        "date": "2024-06-26",
        "entity": {"series_id": "s1_p1", "category": "fruit"},
        "mu": 20.0,
        "revenue_scale": 90.0,
        "economics": {
            "price": 4.5,
            "unit_cost": 2.7,
            "shelf_life": 4,
            "holding": 0.05,
            "disposal": 0.1,
            "goodwill": 0.6,
            "terminal_waste_risk": 0.25,
        },
        "state": {
            "recorded_on_hand_by_age": [6, 3, 0, 0],
            "verified_on_hand_by_age": [6, 0, 0, 0],
            "pipeline_by_day": [0, 0, 0, 0],
        },
        "current_terms": context()["constraints"],
        "approval_threshold": 130.0,
        "max_expedite_share": 0.6,
        "freshness_max_age_hours": 30,
        "data_age_hours": 24,
        "history_days_missing": 0,
        "signals": {},
        "investigation_cost": 2.7,
        "review_cost": 5.4,
        "forecast": {"levels": LEVELS, "quantiles": q},
        "scenarios": rng.gamma(6, 20 / 6, (80, 3)).round(3).tolist(),
        "candidate": {"orders": [18.0, 0.0, 0.0]},
    }
    vp = ValidatorParams(n_scenarios=80)
    a = studio_evaluate(case, {"risk_weight": 0.0}, vp)
    assert a["recommended"]["expected"] == a["best_expected"]["expected"]
    b = studio_evaluate(case, {"risk_weight": 0.9}, vp)
    assert b["recommended"]["cvar"] <= a["recommended"]["cvar"] + 1e-9
    c = studio_evaluate(case, {"alternate_eligible": False}, vp)
    assert c["recommended"]["orders"][1] == 0.0
    d = studio_evaluate(case, {"demand_shift": 0.4}, vp)
    assert sum(d["recommended"]["orders"]) >= sum(a["recommended"]["orders"]) - 1e-9
