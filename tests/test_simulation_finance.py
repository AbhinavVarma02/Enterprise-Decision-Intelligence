"""Inventory conservation, FIFO perishability, financial accounting and risk aggregation."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from edi.finance.economics import CostBreakdown, UnitEconomics
from edi.simulation.engine import cvar, evaluate_actions, step

ECON = UnitEconomics(
    price=4.0, unit_cost=2.5, shelf_life=3, holding=0.05, disposal=0.1, goodwill=0.5, terminal_waste_risk=0.3
)

amounts = st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False)


@settings(max_examples=150, deadline=None)
@given(st.lists(amounts, min_size=3, max_size=3), amounts, amounts)
def test_step_conserves_units_and_stays_nonnegative(cohorts, arrival, demand) -> None:
    inv = np.array(cohorts, dtype=float)
    start = inv.sum() + arrival
    out = step(inv, np.array(arrival), np.array(demand), ECON)
    assert float(out["sales"] + out["waste"] + out["end_units"]) == pytest.approx(start, rel=1e-9, abs=1e-9)
    assert (inv >= -1e-12).all()
    assert float(out["sales"]) <= demand + 1e-9
    assert float(out["sales"] + out["lost"]) == pytest.approx(demand)
    assert inv[0] == 0.0  # survivors have aged by one day


def test_fifo_sells_oldest_first_and_wastes_only_expiring_units() -> None:
    inv = np.array([10.0, 5.0, 3.0])  # ages 0, 1, 2; age 2 expires tonight
    out = step(inv, np.array(0.0), np.array(4.0), ECON)
    assert float(out["waste"]) == 0.0  # 3 oldest sold first, then 1 of age 1
    np.testing.assert_allclose(inv, [0.0, 10.0, 4.0])
    out = step(inv, np.array(0.0), np.array(1.0), ECON)
    assert float(out["waste"]) == pytest.approx(3.0)  # age-2 cohort had 4, one sold


def test_shelf_life_one_must_sell_on_arrival_day() -> None:
    econ = UnitEconomics(4.0, 2.5, 1, 0.05, 0.1, 0.5, 0.3)
    inv = np.zeros(1)
    out = step(inv, np.array(10.0), np.array(4.0), econ)
    assert float(out["waste"]) == 6.0 and float(out["end_units"]) == 0.0


def test_zero_demand_and_extreme_quantities() -> None:
    res = evaluate_actions(
        np.zeros(3),
        np.zeros(2),
        np.array([[0, 0, 0], [1e6, 0, 0]]),
        np.array([1, 1, 0]),
        np.array([2.5, 2.8, 3.4]),
        np.zeros((5, 2)),
        ECON,
    )
    assert np.allclose(res.cost[0], 0.0)
    assert np.isfinite(res.cost).all()
    assert res.procurement[1] == pytest.approx(2.5e6)


def test_horizon_cost_decomposes_exactly() -> None:
    cohorts = np.array([2.0, 1.0, 4.0])
    orders = np.array([[3.0, 1.0, 2.0]])
    leads, costs = np.array([1, 1, 0]), np.array([2.5, 2.8, 3.4])
    demand = np.array([[5.0, 6.0]])
    res = evaluate_actions(cohorts, np.zeros(2), orders, leads, costs, demand, ECON)
    inv = cohorts.copy()
    total = float((orders @ costs)[0])
    for t, arr in enumerate([2.0, 4.0]):
        o = step(inv, np.array(arr), np.array(demand[0, t]), ECON)
        total += float(o["holding"] + o["disposal"] + o["shortage"])
    total += ECON.terminal_charge * inv.sum()
    assert float(res.cost[0, 0]) == pytest.approx(total)


def test_cost_identity_total_equals_price_times_demand_minus_profit() -> None:
    cb = CostBreakdown(
        procurement=50,
        holding=2,
        disposal=1,
        lost_revenue=12,
        goodwill=1.5,
        governance=3,
        terminal_adjustment=-4,
        revenue=88,
        demand_units=25,
        sales_units=22,
        lost_units=3,
    )
    assert cb.total == pytest.approx(4.0 * cb.demand_units - cb.profit)  # price 4 x demand


def test_no_double_counting_of_shortage() -> None:
    """One unit short costs price + goodwill once; procurement for it is never incurred."""
    res = evaluate_actions(
        np.zeros(3),
        np.zeros(2),
        np.zeros((1, 3)),
        np.array([1, 1, 0]),
        np.array([2.5, 2.8, 3.4]),
        np.array([[1.0, 0.0]]),
        ECON,
    )
    assert float(res.cost[0, 0]) == pytest.approx(ECON.price + ECON.goodwill)


def test_terminal_charge_values_leftover_at_expected_replacement() -> None:
    # ordering one extra unit that is left over costs r x (c + w) + h
    assert ECON.unit_cost + ECON.terminal_charge == pytest.approx(0.3 * (2.5 + 0.1) + 0.05)
    assert ECON.terminal_charge < 0


def test_cvar_matches_definition(rng) -> None:
    x = rng.normal(size=1000)
    worst = np.sort(x)[-100:].mean()
    assert float(cvar(x, 0.9)) == pytest.approx(worst)
    assert float(cvar(np.array([1.0, 2.0, 3.0, 4.0]), 0.5)) == pytest.approx(3.5)
    assert float(cvar(np.array([1.0, 2.0, 3.0]), 0.5)) == pytest.approx((3 + 0.5 * 2) / 1.5)
    assert (cvar(np.vstack([x, x + 1]), 0.9) >= np.array([x.mean(), x.mean() + 1])).all()
