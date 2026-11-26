"""Decision policies P1-P4 and the retrospective oracle.

Policies only see a `DecisionInputs` snapshot: recorded inventory (may be wrong), known pipeline,
the supplier snapshot (may be stale), forecasts built from data available at decision time, and the
simulation end day. None of them can see realized demand; the oracle can, and is labeled as a
retrospective bound.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from edi.finance.economics import SupplyContext, UnitEconomics
from edi.optimization.milp import solve
from edi.simulation.engine import horizon_for
from edi.simulation.scenarios import sample_paths, stream

Z90 = 2.5631031310892007  # width of a central 80% normal interval in standard deviations


@dataclass
class Forecast:
    model: str
    point: np.ndarray  # (H,)
    q: np.ndarray  # (H, n_levels)
    levels: list[float]
    origin: int
    staleness_days: int = 0


@dataclass
class DecisionInputs:
    series_id: str
    day: int
    last_day: int
    cohorts: np.ndarray  # recorded on-hand by age
    pipeline: np.ndarray  # scheduled arrivals by day offset 0..3 (as recorded)
    supply: SupplyContext  # snapshot the planning system uses
    econ: UnitEconomics
    mu: float
    forecasts: dict[str, Forecast]
    n_scenarios: int
    rho: float
    seed: int
    data_age_hours: float = 24.0
    history_days_missing: int = 0

    def capped_supply(self) -> SupplyContext:
        """Disallow arrivals after the simulation end (identical for every policy)."""
        sup = self.supply
        for s in sup.suppliers:
            if self.day + s.lead > self.last_day and s.capacity > 0:
                sup = sup.with_supplier(s.name, capacity=0.0)
        return sup


@dataclass
class PolicyDecision:
    policy: str
    orders: np.ndarray
    status: str
    expected_cost: float | None
    cvar: float | None
    forecast_model: str
    objective: str
    solve_ms: float
    horizon: int
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""


def scenarios_for(inp: DecisionInputs, model: str, horizon: int, purpose: str) -> np.ndarray:
    fc = inp.forecasts[model]
    q = fc.q[:horizon]
    rng = stream(inp.seed, inp.series_id, inp.day, purpose, model)
    return sample_paths(q, fc.levels, inp.n_scenarios, inp.rho, rng)


def _horizon(sup: SupplyContext) -> int:
    return horizon_for(sup.leads, sup.capacities)


def base_stock(inp: DecisionInputs, z: float, model: str = "moving_average") -> PolicyDecision:
    """P1: order-up-to policy on observed-sales forecasts with a tuned safety factor."""
    t0 = time.perf_counter()
    sup = inp.capped_supply()
    fc = inp.forecasts[model]
    lead = int(sup.suppliers[0].lead)
    cover = min(lead, len(fc.point) - 1)
    mu_t = fc.point[: cover + 1]
    sigma_t = np.maximum(
        (fc.q[: cover + 1, fc.levels.index(0.9)] - fc.q[: cover + 1, fc.levels.index(0.1)]) / Z90, 0
    )
    target = float(mu_t.sum() + z * np.sqrt((sigma_t**2).sum()))
    on_hand = float(inp.cohorts.sum())
    position = on_hand + float(inp.pipeline[: cover + 1].sum())
    need = max(0.0, target - position)
    caps = sup.capacities
    q = np.zeros(3)
    moq = sup.suppliers[0].moq
    if caps[0] > 0 and need > 0:
        q[0] = min(need, caps[0])
        if q[0] < moq:
            q[0] = moq if q[0] >= 0.5 * moq and moq <= caps[0] else 0.0
    remaining = max(0.0, need - q[0])
    q[1] = min(remaining, caps[1])
    today_target = float(fc.point[0] + z * sigma_t[0])
    today_avail = on_hand + float(inp.pipeline[0])
    if today_avail < today_target and caps[2] > 0:
        q[2] = min(today_target - today_avail, caps[2])
    q = _fit_budget(q, sup)
    return PolicyDecision(
        "P1_base_stock", q, "rule", None, None, model, "rule", (time.perf_counter() - t0) * 1e3, cover + 1
    )


def _fit_budget(q: np.ndarray, sup: SupplyContext) -> np.ndarray:
    """Trim alternate, then expedite, then primary until spend fits the budget."""
    q = q.copy()
    costs = sup.unit_costs
    for s in (1, 2, 0):
        over = q @ costs - sup.budget
        if over <= 1e-9:
            break
        q[s] = max(0.0, q[s] - over / costs[s])
    if 0 < q[0] < sup.suppliers[0].moq:
        q[0] = 0.0
    return q


def milp_policy(
    inp: DecisionInputs,
    name: str,
    model: str,
    objective: str = "expected",
    alpha: float = 0.9,
    lam: float = 0.5,
    deterministic: bool = False,
    supply: SupplyContext | None = None,
    cohorts: np.ndarray | None = None,
) -> PolicyDecision:
    t0 = time.perf_counter()
    sup = supply if supply is not None else inp.capped_supply()
    h = _horizon(sup)
    if deterministic:
        demand = inp.forecasts[model].point[:h][None, :]
    else:
        demand = scenarios_for(inp, model, h, "policy")
    coh = inp.cohorts if cohorts is None else cohorts
    res = solve(coh, inp.pipeline[:h], sup, demand, inp.econ, objective=objective, alpha=alpha, lam=lam)
    return PolicyDecision(
        policy=name,
        orders=res.orders,
        status=res.status,
        expected_cost=res.expected_cost,
        cvar=res.cvar,
        forecast_model=model,
        objective=objective if not deterministic else "deterministic",
        solve_ms=(time.perf_counter() - t0) * 1e3,
        horizon=h,
        note=res.message if not res.ok else "",
    )


def oracle(
    true_cohorts: np.ndarray,
    pipeline: np.ndarray,
    supply: SupplyContext,
    realized: np.ndarray,
    econ: UnitEconomics,
    day: int,
    last_day: int,
) -> PolicyDecision:
    """Retrospective reference: realized demand, true state, authoritative constraints. Not deployable."""
    t0 = time.perf_counter()
    sup = supply
    for s in sup.suppliers:
        if day + s.lead > last_day:
            sup = sup.with_supplier(s.name, capacity=0.0)
    h = _horizon(sup)
    d = np.zeros(h)
    d[: min(h, len(realized))] = realized[:h]
    res = solve(true_cohorts, pipeline[:h], sup, d[None, :], econ)
    return PolicyDecision(
        "ORACLE",
        res.orders,
        res.status,
        res.expected_cost,
        None,
        "realized",
        "oracle",
        (time.perf_counter() - t0) * 1e3,
        h,
    )


def with_supply(inp: DecisionInputs, supply: SupplyContext) -> DecisionInputs:
    return replace(inp, supply=supply)
