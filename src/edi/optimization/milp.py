"""Scenario-based replenishment MILP solved with HiGHS (scipy.optimize.milp).

Decision variables: order quantities q_s for s in (primary, alternate, expedite); a binary y_s for each
supplier with a minimum order quantity; per scenario k, day t and inventory cohort c, the units x_ktc
sold from that cohort; for the risk-aware objective, the CVaR auxiliaries eta and u_k.

Cohorts are the on-hand age groups plus one cohort per arrival day (existing pipeline plus any order
with that lead time). A cohort can sell from its arrival day through its expiry day. Waste and end
inventory are equalities in the sales variables, so the model cannot discard stock that the simulator
would keep; with holding cost identical across cohorts, an optimal allocation sells oldest first and
the objective equals the FIFO simulator's cost for the same orders (tested).

Scenario cost (linear):
    procurement + sum_t [holding x surviving units + (price + goodwill) x unmet demand]
    + disposal x expired units + terminal charge x units left after the last day
Expected objective: mean over scenarios. Risk-aware: (1 - lambda) mean + lambda CVaR_alpha
(Rockafellar and Uryasev, 2000).

Hard constraints: capacity (0 for unavailable or ineligible suppliers and for arrivals beyond the
horizon), MOQ through binaries, budget, optional minimum commitment to the primary supplier, optional
cap on expected shortage. Hard constraints are never relaxed: an infeasible model returns status
"infeasible" and no action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from edi.finance.economics import SupplyContext, UnitEconomics
from edi.simulation.engine import cvar as _cvar


@dataclass
class SolveResult:
    status: str  # optimal | infeasible | error
    orders: np.ndarray  # (3,)
    objective: float | None
    expected_cost: float | None
    cvar: float | None
    message: str
    n_vars: int = 0
    n_cons: int = 0
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "optimal"


def solve(
    cohorts: np.ndarray,
    pipeline: np.ndarray,
    supply: SupplyContext,
    demand: np.ndarray,
    econ: UnitEconomics,
    *,
    objective: str = "expected",
    alpha: float = 0.9,
    lam: float = 0.5,
    time_limit: float = 10.0,
) -> SolveResult:
    demand = np.atleast_2d(np.asarray(demand, dtype=float))
    K, H = demand.shape
    L = econ.shelf_life
    leads = supply.leads
    caps = supply.capacities.copy()
    caps[leads >= H] = 0.0
    costs = supply.unit_costs
    moqs = supply.moqs
    pipe = np.zeros(H)
    pipeline = np.asarray(pipeline, dtype=float)
    pipe[: min(H, len(pipeline))] = pipeline[:H]
    cohorts = np.asarray(cohorts, dtype=float)
    if supply.min_commitment > caps[0] + 1e-9:
        return _infeasible("minimum commitment exceeds usable primary capacity", 0, 0)

    # Cohort table: (arrival day, expiry day, constant quantity, order coefficients (3,))
    coh: list[tuple[int, int, float, np.ndarray]] = []
    for a in range(L):
        if cohorts[a] > 0:
            coh.append((0, L - 1 - a, float(cohorts[a]), np.zeros(3)))
    for tau in range(H):
        coef = np.array([1.0 if (leads[s] == tau and caps[s] > 0) else 0.0 for s in range(3)])
        if pipe[tau] > 0 or coef.any():
            coh.append((tau, tau + L - 1, float(pipe[tau]), coef))
    C = len(coh)

    binaries = [s for s in range(3) if moqs[s] > 0 and caps[s] > 0]
    nb = len(binaries)
    active = [(t, c) for c, (arr, ex, _, _) in enumerate(coh) for t in range(arr, min(ex, H - 1) + 1)]
    na = len(active)
    i_q, i_b, i_x = 0, 3, 3 + nb
    risk = objective == "cvar"
    i_eta = i_x + K * na
    i_u = i_eta + 1
    n = i_x + K * na + ((1 + K) if risk else 0)
    pos = {tc: j for j, tc in enumerate(active)}

    h, w, short, kappa = econ.holding, econ.disposal, econ.shortage_cost, econ.terminal_charge
    # Per-scenario cost = const_k + qcoef . q + xcoef . x_k (xcoef identical across scenarios)
    qcoef = costs.astype(float).copy()
    const_q = 0.0
    xcoef = np.zeros(na)
    for c, (arr, ex, qty, oc) in enumerate(coh):
        # units of cohort c alive at end of day t (arr <= t < ex) are held; at H-1 also terminal
        for t in range(arr, min(ex, H) if ex < H else H):
            if t >= ex:
                continue
            weight = h + (kappa if t == H - 1 else 0.0)
            const_q += weight * qty
            qcoef += weight * oc
            for tau in range(arr, t + 1):
                xcoef[pos[(tau, c)]] -= weight
        if ex <= H - 1:  # expires inside the horizon: unsold units are wasted
            const_q += w * qty
            qcoef += w * oc
            for tau in range(arr, ex + 1):
                xcoef[pos[(tau, c)]] -= w
    for j in range(len(active)):
        xcoef[j] -= short
    scen_const = const_q + short * demand.sum(axis=1)

    c_vec = np.zeros(n)
    wmean = (1 - lam) if risk else 1.0
    c_vec[i_q : i_q + 3] = wmean * qcoef
    for k in range(K):
        c_vec[i_x + k * na : i_x + (k + 1) * na] = wmean * xcoef / K
    if risk:
        c_vec[i_eta] = lam
        c_vec[i_u : i_u + K] = lam / ((1 - alpha) * K)

    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    lb: list[float] = []
    ub: list[float] = []
    r = 0

    def add(entries: list[tuple[int, float]], lo: float, hi: float) -> None:
        nonlocal r
        for j, v in entries:
            rows.append(r)
            cols.append(j)
            vals.append(v)
        lb.append(lo)
        ub.append(hi)
        r += 1

    by_day: dict[int, list[int]] = {}
    by_coh: dict[int, list[int]] = {}
    for j, (t, c) in enumerate(active):
        by_day.setdefault(t, []).append(j)
        by_coh.setdefault(c, []).append(j)
    for k in range(K):
        base = i_x + k * na
        for t in range(H):
            js = by_day.get(t, [])
            if js:
                add([(base + j, 1.0) for j in js], -np.inf, float(demand[k, t]))
        for cidx, (_, _, qty, oc) in enumerate(coh):
            js = by_coh.get(cidx, [])
            ent = [(base + j, 1.0) for j in js] + [(i_q + s, -oc[s]) for s in range(3) if oc[s]]
            add(ent, -np.inf, qty)
        if risk:
            ent = [(i_u + k, 1.0), (i_eta, 1.0)]
            ent += [(i_q + s, -qcoef[s]) for s in range(3) if qcoef[s]]
            ent += [(base + j, -xcoef[j]) for j in range(na) if xcoef[j]]
            add(ent, float(scen_const[k]), np.inf)
    add([(i_q + s, float(costs[s])) for s in range(3)], -np.inf, float(supply.budget))
    for jb, s in enumerate(binaries):
        add([(i_q + s, 1.0), (i_b + jb, -float(moqs[s]))], 0.0, np.inf)
        add([(i_q + s, 1.0), (i_b + jb, -float(caps[s]))], -np.inf, 0.0)
    if supply.max_expected_shortage is not None:
        ent = [(i_x + k * na + j, 1.0 / K) for k in range(K) for j in range(na)]
        add(ent, float(demand.sum() / K - supply.max_expected_shortage), np.inf)

    lo_b = np.zeros(n)
    hi_b = np.full(n, np.inf)
    hi_b[i_q : i_q + 3] = caps
    lo_b[i_q] = supply.min_commitment
    hi_b[i_b : i_b + nb] = 1.0
    if risk:
        lo_b[i_eta] = -np.inf
    integrality = np.zeros(n)
    integrality[i_b : i_b + nb] = 1
    A = coo_matrix((vals, (rows, cols)), shape=(r, n)).tocsr()
    res = milp(
        c_vec,
        constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
        bounds=Bounds(lo_b, hi_b),
        integrality=integrality,
        options={"time_limit": time_limit, "presolve": True, "mip_rel_gap": 1e-7},
    )
    if res.status == 2 or (res.x is None and "infeasible" in str(res.message).lower()):
        return _infeasible(str(res.message), n, r)
    if res.x is None or res.status != 0:
        return SolveResult("error", np.zeros(3), None, None, None, str(res.message), n, r)
    x = res.x
    q = np.clip(x[i_q : i_q + 3], 0.0, None)
    q[q < 1e-9] = 0.0
    xs = x[i_x : i_x + K * na].reshape(K, na)
    scen = scen_const + qcoef @ x[i_q : i_q + 3] + xs @ xcoef
    const = wmean * scen_const.mean()
    return SolveResult(
        status="optimal",
        orders=q,
        objective=float(res.fun + const),
        expected_cost=float(scen.mean()),
        cvar=float(_cvar(scen, alpha)),
        message=str(res.message),
        n_vars=n,
        n_cons=r,
        info={"horizon": H, "scenarios": K, "objective": objective, "cohorts": C},
    )


def _infeasible(msg: str, n: int, r: int) -> SolveResult:
    return SolveResult("infeasible", np.zeros(3), None, None, None, msg, n, r)


def action_grid(
    supply: SupplyContext, horizon: int, n_primary: int = 12, n_alt: int = 6, n_exp: int = 5
) -> np.ndarray:
    """Bounded candidate grid used for brute-force checks, VOI and the browser evaluator."""
    caps = supply.capacities.copy()
    caps[supply.leads >= horizon] = 0.0
    quantities = []
    for cap, moq, count in zip(caps, supply.moqs, (n_primary, n_alt, n_exp)):
        choices = np.linspace(moq, cap, count) if cap > 0 and cap >= moq else np.array([0.0])
        quantities.append(np.unique(np.r_[0.0, choices]))
    grid = np.array(np.meshgrid(*quantities, indexing="ij")).reshape(3, -1).T
    spend = grid @ supply.unit_costs
    grid = grid[spend <= supply.budget + 1e-9]
    if supply.min_commitment > 0:
        grid = grid[grid[:, 0] >= supply.min_commitment - 1e-9]
    return grid
