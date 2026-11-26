"""MILP correctness against the simulator, brute force and an analytical newsvendor solution."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from edi.finance.economics import base_supply_context, economics_for
from edi.optimization.milp import action_grid, solve
from edi.simulation.engine import cvar, evaluate_actions, horizon_for


def _case(cfg, profile, seed, k=60):
    econ = economics_for(profile, cfg)
    sup = base_supply_context(20.0, econ, cfg, 1)
    rng = np.random.default_rng(seed)
    h = horizon_for(sup.leads, sup.capacities)
    demand = rng.gamma(5, 4.0, size=(k, h))
    coh = np.zeros(econ.shelf_life)
    coh[-1], coh[0] = 4.0, 7.0
    pipe = np.zeros(h)
    pipe[1] = 3.0
    return econ, sup, demand, coh, pipe


@pytest.mark.parametrize("profile", ["leafy", "fruit", "dairy", "protein"])
@pytest.mark.parametrize("objective", ["expected", "cvar"])
def test_milp_objective_matches_fifo_simulator(base_cfg, profile, objective) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, profile, 3)
    res = solve(coh, pipe, sup, demand, econ, objective=objective)
    assert res.ok
    sim = evaluate_actions(coh, pipe, res.orders[None, :], sup.leads, sup.unit_costs, demand, econ).cost[0]
    sim_obj = sim.mean() if objective == "expected" else 0.5 * sim.mean() + 0.5 * float(cvar(sim, 0.9))
    if econ.shelf_life >= 3:
        assert res.objective == pytest.approx(sim_obj, rel=1e-7, abs=1e-6)
    else:
        # two-day shelf life: the LP may allocate sales slightly better than FIFO in rare cases where
        # carrying an expiring unit one more night only adds holding cost; the gap is bounded by holding
        assert res.objective <= sim_obj + 1e-7
        assert sim_obj - res.objective <= econ.holding * demand.sum(axis=1).max()


@pytest.mark.parametrize("profile", ["fruit", "protein"])
def test_milp_beats_or_ties_exhaustive_grid(base_cfg, profile) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, profile, 8)
    res = solve(coh, pipe, sup, demand, econ)
    grid = action_grid(sup, demand.shape[1], 30, 10, 8)
    g = evaluate_actions(coh, pipe, grid, sup.leads, sup.unit_costs, demand, econ).cost.mean(axis=1)
    assert res.expected_cost <= g.min() + 1e-7
    assert res.expected_cost >= g.min() - 0.05 * abs(g.min())  # and not implausibly far below it


def test_grid_enforces_minimums_for_each_supplier(base_cfg) -> None:
    econ, sup, demand, _, _ = _case(base_cfg, "fruit", 8)
    sup = sup.with_supplier("primary", capacity=2.0).with_supplier("alternate", moq=5.0)
    grid = action_grid(sup, demand.shape[1])
    assert (grid[:, 0] == 0).all()
    assert (grid[:, 1] > 0).any()
    assert ((grid[:, 1] == 0) | (grid[:, 1] >= 5)).all()
    assert (grid @ sup.unit_costs <= sup.budget + 1e-9).all()


def test_newsvendor_critical_fractile(base_cfg) -> None:
    """Expedite-only single-period problem has the classic SAA solution."""
    econ = economics_for("fruit", base_cfg)
    sup = base_supply_context(20.0, econ, base_cfg, 1)
    sup = sup.with_supplier("primary", eligible=False).with_supplier("alternate", eligible=False)
    sup = sup.with_supplier("expedite", capacity=1e4)
    sup = replace(sup, budget=1e9)
    rng = np.random.default_rng(11)
    k = 201
    demand = np.column_stack([rng.gamma(4, 5.0, size=k), np.zeros(k)])
    res = solve(np.zeros(econ.shelf_life), np.zeros(2), sup, demand, econ)
    ce = sup.unit_costs[2]
    under = econ.price + econ.goodwill - ce
    over = ce + 2 * econ.holding + econ.terminal_charge
    tau = under / (under + over)
    expected = np.sort(demand[:, 0])[math.ceil(tau * k) - 1]
    assert res.orders[2] == pytest.approx(expected, abs=1e-6)
    assert res.orders[0] == 0 and res.orders[1] == 0


def test_hard_constraints_hold_and_moq_is_respected(base_cfg) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, "dairy", 5)
    sup = sup.with_supplier("alternate", eligible=False)
    sup = replace(sup, budget=30.0)
    res = solve(coh, pipe, sup, demand * 3, econ)
    assert res.ok
    q = res.orders
    assert q[1] == 0.0
    assert q @ sup.unit_costs <= 30.0 + 1e-6
    assert q[0] == 0.0 or q[0] >= sup.suppliers[0].moq - 1e-6
    assert (q <= sup.capacities + 1e-6).all()


def test_infeasibility_is_explicit_and_never_relaxed(base_cfg) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, "fruit", 2)
    too_much = replace(sup, min_commitment=sup.suppliers[0].capacity * 2)
    res = solve(coh, pipe, too_much, demand, econ)
    assert res.status == "infeasible" and not res.orders.any()
    pricey = replace(sup, min_commitment=30.0, budget=10.0)
    res = solve(coh, pipe, pricey, demand, econ)
    assert res.status == "infeasible" and res.expected_cost is None
    no_short = replace(sup, max_expected_shortage=0.0)
    res = solve(coh, pipe, no_short.with_supplier("expedite", capacity=0.0), demand * 5, econ)
    assert res.status == "infeasible"


def test_solver_is_deterministic(base_cfg) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, "protein", 4)
    a = solve(coh, pipe, sup, demand, econ, objective="cvar")
    b = solve(coh, pipe, sup, demand, econ, objective="cvar")
    np.testing.assert_array_equal(a.orders, b.orders)


def test_risk_aware_objective_lowers_tail(base_cfg) -> None:
    econ, sup, demand, coh, pipe = _case(base_cfg, "protein", 9, k=120)
    e = solve(coh, pipe, sup, demand, econ, objective="expected")
    c = solve(coh, pipe, sup, demand, econ, objective="cvar", lam=0.9)
    assert c.cvar <= e.cvar + 1e-7
    assert c.expected_cost >= e.expected_cost - 1e-7
