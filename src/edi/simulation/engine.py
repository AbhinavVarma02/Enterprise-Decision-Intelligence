"""Perishable inventory engine: the reference evaluator shared by policies, validation, the benchmark
and (through golden fixtures) the browser.

Event order within a day:
  1. arrivals due today join the shelf as age 0
  2. demand is served from the oldest units first (FIFO)
  3. units of age shelf_life - 1 that remain are wasted at close
  4. holding is charged on the units that survive the night; survivors age by one day

`cohorts[a]` holds units of age a at the start of the day, before arrivals.
Orders are vectors [primary, alternate, expedite]; expedite (lead 0) arrives before trading today.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from edi.finance.economics import CostBreakdown, UnitEconomics

MAX_HORIZON = 4


def step(inv: np.ndarray, arrivals: np.ndarray, demand: np.ndarray, econ: UnitEconomics) -> dict[str, np.ndarray]:
    """Advance one day in place. inv has shape (..., L); arrivals and demand broadcast to inv[..., 0]."""
    inv[..., 0] += arrivals
    remaining = np.broadcast_to(demand, inv.shape[:-1]).astype(float).copy()
    for a in range(inv.shape[-1] - 1, -1, -1):
        take = np.minimum(inv[..., a], remaining)
        inv[..., a] -= take
        remaining -= take
    sales = np.broadcast_to(demand, remaining.shape) - remaining
    waste = inv[..., -1].copy()
    inv[..., -1] = 0.0
    end_units = inv.sum(axis=-1)
    if inv.shape[-1] > 1:
        inv[..., 1:] = inv[..., :-1].copy()
    inv[..., 0] = 0.0
    return {
        "sales": sales,
        "lost": remaining,
        "waste": waste,
        "end_units": end_units,
        "holding": econ.holding * end_units,
        "disposal": econ.disposal * waste,
        "shortage": econ.shortage_cost * remaining,
    }


def horizon_for(leads: np.ndarray, capacities: np.ndarray) -> int:
    usable = leads[capacities > 0]
    lead = int(usable.max()) if len(usable) else 0
    return int(min(MAX_HORIZON, max(2, lead + 1)))


@dataclass
class HorizonResult:
    cost: np.ndarray  # (A, K) total horizon cost incl. procurement and terminal charge
    procurement: np.ndarray  # (A,)
    shortage_units: np.ndarray  # (A, K)
    waste_units: np.ndarray  # (A, K)
    end_units: np.ndarray  # (A, K)


def evaluate_actions(
    cohorts: np.ndarray,
    pipeline: np.ndarray,
    orders: np.ndarray,
    leads: np.ndarray,
    unit_costs: np.ndarray,
    demand: np.ndarray,
    econ: UnitEconomics,
) -> HorizonResult:
    """Evaluate A candidate order vectors over K demand scenarios of H days.

    cohorts: (L,) on-hand by age; pipeline: (H,) already-scheduled arrivals by day offset;
    orders: (A, 3); leads: (3,); unit_costs: (3,); demand: (K, H).
    """
    orders = np.atleast_2d(np.asarray(orders, dtype=float))
    demand = np.atleast_2d(np.asarray(demand, dtype=float))
    n_a, (n_k, n_h) = orders.shape[0], demand.shape
    L = econ.shelf_life
    if len(cohorts) != L:
        raise ValueError(f"cohorts length {len(cohorts)} != shelf life {L}")
    inv = np.broadcast_to(np.asarray(cohorts, dtype=float), (n_a, n_k, L)).copy()
    cost = np.zeros((n_a, n_k))
    short = np.zeros((n_a, n_k))
    waste = np.zeros((n_a, n_k))
    out: dict[str, np.ndarray] = {}
    for t in range(n_h):
        arr = np.full(n_a, float(pipeline[t]) if t < len(pipeline) else 0.0)
        for s in range(3):
            if int(leads[s]) == t:
                arr = arr + orders[:, s]
        out = step(inv, arr[:, None], demand[None, :, t], econ)
        cost += out["holding"] + out["disposal"] + out["shortage"]
        short += out["lost"]
        waste += out["waste"]
    end_units = out["end_units"]
    procurement = orders @ np.asarray(unit_costs, dtype=float)
    cost += econ.terminal_charge * end_units + procurement[:, None]
    return HorizonResult(cost=cost, procurement=procurement, shortage_units=short, waste_units=waste, end_units=end_units)


def cvar(costs: np.ndarray, alpha: float, axis: int = -1) -> np.ndarray:
    """Discrete CVaR: mean of the worst (1 - alpha) share of equally weighted outcomes (Rockafellar-Uryasev)."""
    c = np.sort(costs, axis=axis)
    n = c.shape[axis]
    k = (1 - alpha) * n
    full = int(np.floor(k))
    frac = k - full
    c = np.moveaxis(c, axis, -1)[..., ::-1]
    tail = c[..., :full].sum(axis=-1)
    if frac > 1e-12 and full < n:
        tail = tail + frac * c[..., full]
    return tail / k


def day_costs(out: dict[str, np.ndarray], econ: UnitEconomics, demand: float, arrivals: float) -> CostBreakdown:
    """Cost breakdown for one simulated day of a single trajectory (scalars)."""
    sales = float(np.asarray(out["sales"]).sum())
    lost = float(np.asarray(out["lost"]).sum())
    waste = float(np.asarray(out["waste"]).sum())
    end_units = float(np.asarray(out["end_units"]).sum())
    return CostBreakdown(
        holding=econ.holding * end_units,
        disposal=econ.disposal * waste,
        lost_revenue=econ.price * lost,
        goodwill=econ.goodwill * lost,
        revenue=econ.price * sales,
        demand_units=float(demand),
        sales_units=sales,
        lost_units=lost,
        waste_units=waste,
        received_units=float(arrivals),
        inventory_value_days=econ.unit_cost * end_units,
        days=1,
    )
