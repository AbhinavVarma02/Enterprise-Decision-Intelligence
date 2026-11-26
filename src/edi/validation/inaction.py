"""Cost of inaction: compare acting now with a smaller order, waiting a day, escalating and doing nothing.

All options are evaluated over the decision horizon (today through the arrival day of a standard order)
on the same demand scenarios. When waiting pushes an order's arrival to the end of the horizon or later,
those units cannot serve demand inside it; they are charged at purchase cost and credited as leftover
stock at the terminal value, exactly like any other stock left at the end of the horizon.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from edi.finance.economics import SupplyContext, UnitEconomics
from edi.simulation.engine import cvar, evaluate_actions


def alternatives(
    candidate: np.ndarray,
    cohorts: np.ndarray,
    pipeline: np.ndarray,
    supply: SupplyContext,
    econ: UnitEconomics,
    scenarios: np.ndarray,
    review_cost: float,
    alpha: float = 0.9,
    tolerance_margin: float | None = None,
) -> list[dict[str, Any]]:
    h = scenarios.shape[1]
    pipe = np.zeros(h)
    pipe[: min(h, len(pipeline))] = np.asarray(pipeline)[:h]
    leads = supply.leads.copy()
    costs = supply.unit_costs
    caps = supply.capacities
    cand = np.minimum(candidate, caps)
    smaller = cand.copy()
    smaller[:2] *= 0.5
    smaller[2] = 0.0
    if 0 < smaller[0] < supply.suppliers[0].moq:
        smaller[0] = supply.suppliers[0].moq if supply.suppliers[0].moq <= caps[0] else 0.0
    options = [
        ("act_now", "Act now", cand, leads, 0.0),
        ("smaller", "Smaller reversible order", smaller, leads, 0.0),
        ("wait", "Wait one day, then order", cand, leads + 1, 0.0),
        ("escalate", "Escalate for same-day review", cand, leads, review_cost),
        ("no_action", "No action", np.zeros(3), leads, 0.0),
    ]
    demand = scenarios.sum(axis=1)
    out: list[dict[str, Any]] = []
    tolerance = None
    for key, label, q, ld, extra in options:
        inside = ld < h
        q_in = np.where(inside, q, 0.0)
        q_late = np.where(inside, 0.0, q)
        r = evaluate_actions(cohorts, pipe, q_in[None, :], ld, costs, scenarios, econ)
        late = float(q_late @ costs) + econ.terminal_charge * float(q_late.sum())
        c = r.cost[0] + late + extra
        if tolerance is None and tolerance_margin is not None:
            tolerance = float(c.mean()) + tolerance_margin
        rec: dict[str, Any] = {
            "key": key,
            "label": label,
            "orders": [float(x) for x in q],
            "expected_cost": float(c.mean()),
            "cvar": float(cvar(c, alpha)),
            "p90": float(np.quantile(c, 0.9)),
            "expected_fill_rate": 1.0 - float(np.mean(r.shortage_units[0] / np.maximum(demand, 1e-9))),
            "expected_waste_units": float(r.waste_units[0].mean()),
            "governance_cost": extra,
            "arrives_after_horizon": float(q_late.sum()),
        }
        if tolerance is not None:
            rec["prob_over_tolerance"] = float(np.mean(c > tolerance))
        rec["delta_vs_act_now"] = rec["expected_cost"] - (
            out[0]["expected_cost"] if out else rec["expected_cost"]
        )
        out.append(rec)
    return out
