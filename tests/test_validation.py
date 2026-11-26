"""Validation engine: known-invalid decisions, escalation logic, VOI and the decision contract."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

from edi.finance.economics import base_supply_context, economics_for
from edi.information_value.voi import evpi
from edi.optimization.milp import solve
from edi.simulation.scenarios import sample_paths, stream
from edi.validation.engine import ValidatorParams, validate
from edi.validation.inventory import InventoryAdapter, assumptions_from, build_candidate, constraints_from
from edi.validation.schema import AuthoritativeContext, DecisionCandidate

LEVELS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
ADAPTER = InventoryAdapter()
PARAMS = ValidatorParams(n_scenarios=80)


def _forecast(mu: float = 20.0, h: int = 2) -> np.ndarray:
    base = np.array([0.55, 0.65, 0.82, 1.0, 1.18, 1.38, 1.52]) * mu
    return np.tile(base, (h, 1))


def make_case(
    cfg,
    *,
    orders=None,
    plan_supply=None,
    auth_supply=None,
    cohorts=None,
    age_hours=24.0,
    history_missing=0,
    claimed_scale=1.0,
    signals=None,
    forecast=True,
    mu=20.0,
):
    econ = economics_for("fruit", cfg)
    sup = base_supply_context(mu, econ, cfg, 91)
    plan = plan_supply or sup
    auth = auth_supply or sup
    coh = np.array([6.0, 3.0, 0.0, 0.0]) if cohorts is None else np.asarray(cohorts)
    q = _forecast(mu)
    if orders is None:
        S = sample_paths(q, LEVELS, 80, 0.5, stream("t", "policy"))
        res = solve(coh, np.zeros(2), plan, S, econ)
        orders, claimed = res.orders, res.expected_cost
    else:
        orders, claimed = np.asarray(orders, dtype=float), None
    cand = build_candidate(
        decision_id="test.d91",
        day=91,
        decision_time="2024-06-26T06:00",
        series_id="s1_p1",
        category="fruit",
        mu=mu,
        orders=orders,
        snapshot_supply=plan,
        econ=econ,
        cohorts=coh,
        pipeline=np.zeros(4),
        forecast_q=q if forecast else None,
        levels=LEVELS,
        model_version="test",
        policy_version="test",
        objective="expected",
        expected_cost=None if claimed is None else claimed * claimed_scale,
        cvar_value=None,
        n_scenarios=80,
        age_hours=age_hours,
        history_days_missing=history_missing,
        snapshot_id="snap-1",
    )
    ctx = AuthoritativeContext(
        constraints=constraints_from(auth),
        financial_assumptions=assumptions_from(econ),
        approval_threshold=auth.approval_threshold,
        max_share={"expedite": 0.6},
        freshness_max_age_hours=30,
        signals=signals or {},
        investigation_cost=0.6 * econ.price,
        review_cost=1.2 * econ.price,
    )
    return cand, ctx


def test_sound_decision_is_recommended_with_complete_evidence(base_cfg) -> None:
    cand, ctx = make_case(base_cfg)
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert rep.outcome == "recommend", rep.reasons
    assert [g.gate for g in rep.gates] == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
    assert rep.metrics["expected_cost"] is not None and rep.explanation.startswith("Recommend")


def test_ineligible_supplier_is_rejected(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 91)
    cand, ctx = make_case(
        base_cfg, orders=[10, 8, 0], auth_supply=sup.with_supplier("alternate", eligible=False)
    )
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert rep.outcome == "reject"
    g2 = next(g for g in rep.gates if g.gate == "G2")
    assert g2.status == "fail" and "alternate" in g2.summary
    assert rep.recommended_action is not None and rep.recommended_action["alternate"] == 0.0


def test_capacity_and_budget_breaches_are_rejected(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 91)
    cand, ctx = make_case(base_cfg, orders=[sup.suppliers[0].capacity * 1.5, 0, 0])
    assert validate(cand, ctx, ADAPTER, PARAMS).outcome == "reject"
    cand, ctx = make_case(base_cfg, orders=[20, 0, 0], auth_supply=replace(sup, budget=10.0))
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert rep.outcome == "reject" and "budget" in next(g for g in rep.gates if g.gate == "G2").summary


def test_misreported_cost_fails_financial_consistency(base_cfg) -> None:
    cand, ctx = make_case(base_cfg, claimed_scale=0.4)
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    g3 = next(g for g in rep.gates if g.gate == "G3")
    assert g3.status == "fail" and rep.outcome == "reject"


def test_stale_prices_are_caught_by_assumption_impact(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 91)
    pricier = sup
    for nm in ("primary", "alternate"):
        s = next(x for x in sup.suppliers if x.name == nm)
        pricier = pricier.with_supplier(nm, unit_cost=s.unit_cost * 1.3)
    cand, ctx = make_case(base_cfg, auth_supply=pricier)
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    g3 = next(g for g in rep.gates if g.gate == "G3")
    assert g3.status in ("warn", "fail") and g3.evidence["assumption_impact"] > 0
    assert any("price" in w for w in next(g for g in rep.gates if g.gate == "G2").evidence["warnings"])


def test_stale_data_is_deferred_or_escalated_never_recommended(base_cfg) -> None:
    cand, ctx = make_case(base_cfg, age_hours=72, history_missing=2)
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert rep.outcome in ("defer", "escalate")
    assert next(g for g in rep.gates if g.gate == "G1").status == "fail"
    # plenty of stock on hand makes waiting cheap -> defer
    cand, ctx = make_case(base_cfg, age_hours=72, history_missing=2, cohorts=[40, 20, 0, 0])
    assert validate(cand, ctx, ADAPTER, PARAMS).outcome == "defer"


def test_missing_forecast_blocks_automatic_approval(base_cfg) -> None:
    cand, ctx = make_case(base_cfg, orders=[10, 0, 0], forecast=False)
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert next(g for g in rep.gates if g.gate == "G6").status == "fail"
    assert rep.outcome == "escalate"


def test_phantom_inventory_triggers_investigation(base_cfg) -> None:
    # record claims 30 units carried over although the shelf was empty for 8 hours yesterday
    cand, ctx = make_case(base_cfg, cohorts=[0, 30, 0, 0], signals={"stockout_hours_yesterday": 8})
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert next(g for g in rep.gates if g.gate == "G1").status == "warn"
    v = rep.value_of_information
    assert v is not None and v["value_vs_candidate"] >= v["evpi"] >= 0
    assert rep.outcome == "investigate"


def test_large_spend_requires_approval(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 91)
    cand, ctx = make_case(base_cfg, auth_supply=replace(sup, approval_threshold=1.0))
    rep = validate(cand, ctx, ADAPTER, PARAMS)
    assert rep.outcome == "escalate" and "approval" in rep.reasons[0].lower()


def test_hard_failure_outranks_everything_else(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 91)
    cand, ctx = make_case(
        base_cfg,
        orders=[10, 8, 0],
        auth_supply=sup.with_supplier("alternate", eligible=False),
        age_hours=72,
        cohorts=[0, 30, 0, 0],
        signals={"stockout_hours_yesterday": 8},
    )
    assert validate(cand, ctx, ADAPTER, PARAMS).outcome == "reject"


def test_validator_is_deterministic(base_cfg) -> None:
    cand, ctx = make_case(base_cfg)
    a = validate(cand, ctx, ADAPTER, PARAMS)
    b = validate(cand, ctx, ADAPTER, PARAMS)
    assert a.model_dump() == b.model_dump()


def test_evpi_hand_example() -> None:
    # two actions, two states. a0 good in s0, a1 good in s1.
    costs = np.array([[1.0, 10.0], [6.0, 2.0]])
    res = evpi(costs, np.array([0.5, 0.5]))
    assert res.prior_optimal_cost == pytest.approx(4.0)  # min(5.5, 4.0)
    assert res.perfect_information_cost == pytest.approx(1.5)
    assert res.evpi == pytest.approx(2.5)
    dominated = evpi(np.array([[1.0, 1.0], [2.0, 3.0]]), np.array([0.3, 0.7]))
    assert dominated.evpi == pytest.approx(0.0)
    with pytest.raises(ValueError):
        evpi(costs, np.array([0.5, 0.6]))


def test_schema_rejects_malformed_candidates(base_cfg) -> None:
    cand, _ = make_case(base_cfg)
    payload = cand.model_dump()
    bad = dict(payload, action={"teleport": 3.0})
    with pytest.raises(ValidationError):
        DecisionCandidate.model_validate(bad)
    bad = dict(payload)
    bad["forecast"] = dict(payload["forecast"], quantiles=[[1.0, 2.0]])
    with pytest.raises(ValidationError):
        DecisionCandidate.model_validate(bad)
    bad = dict(payload, decision_id="<script>")
    with pytest.raises(ValidationError):
        DecisionCandidate.model_validate(bad)
    bad = dict(payload, unexpected_field=1)
    with pytest.raises(ValidationError):
        DecisionCandidate.model_validate(bad)
    assert DecisionCandidate.model_validate(payload).decision_id == cand.decision_id
