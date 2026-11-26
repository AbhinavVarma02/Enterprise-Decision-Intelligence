"""Decision Reliability Benchmark: episode simulation for one series under one world and one policy.

Responsibilities:
- build the authoritative world (disruptions, master-data changes) and the planning snapshot (faults)
- run the policy on the snapshot only; for validated policies, run the independent validator
- execute against authoritative terms, record hard-constraint violations, simulate demand
- label every candidate as unsafe or safe using the frozen protocol definition
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from edi.finance.economics import (
    CostBreakdown,
    SupplyContext,
    UnitEconomics,
    base_supply_context,
    economics_for,
)
from edi.optimization.milp import action_grid
from edi.optimization.policies import (
    DecisionInputs,
    Forecast,
    PolicyDecision,
    base_stock,
    milp_policy,
    oracle,
)
from edi.simulation.engine import day_costs, evaluate_actions, horizon_for, step
from edi.simulation.scenarios import WorldScenario, sample_paths, stream
from edi.validation.engine import ValidatorParams, validate
from edi.validation.inventory import InventoryAdapter, assumptions_from, build_candidate, constraints_from
from edi.validation.schema import AuthoritativeContext

ADAPTER = InventoryAdapter()
SHELF_HOURS = 16.0


@dataclass(frozen=True)
class PolicySpec:
    pid: str
    kind: str  # base_stock | deterministic | saa | cvar | validated | oracle
    model: str = "lgbm_quantile_recovered"
    lam: float = 0.5
    z: float = 1.0
    wrapped: str = ""  # saa | cvar for validated policies
    use_voi: bool = True
    use_escalation: bool = True
    risk_review: bool = True
    label: str = ""


@dataclass
class SeriesSetup:
    idx: int
    series_id: str
    profile: str
    econ: UnitEconomics
    mu: float
    reference: np.ndarray  # reference demand by day index (column = day - 1)


class ForecastStore:
    """Fast lookup of precomputed forecasts: (model, series, origin, h) -> point and quantiles."""

    def __init__(self, df: pd.DataFrame, levels: list[float]):
        self.levels = list(levels)
        qcols = [f"q{t}" for t in levels]
        self.o_min = int(df["origin"].min())
        self.h_max = int(df["h"].max())
        n_o = int(df["origin"].max()) - self.o_min + 1
        n_s = int(df["series"].max()) + 1
        self.data: dict[str, np.ndarray] = {}
        for model, g in df.groupby("model"):
            arr = np.full((n_s, n_o, self.h_max, len(levels) + 1), np.nan)
            arr[g["series"].to_numpy(), g["origin"].to_numpy() - self.o_min, g["h"].to_numpy() - 1, 0] = g[
                "point"
            ].to_numpy()
            arr[g["series"].to_numpy(), g["origin"].to_numpy() - self.o_min, g["h"].to_numpy() - 1, 1:] = g[
                qcols
            ].to_numpy()
            self.data[str(model)] = arr

    def get(self, model: str, series: int, day: int, horizon: int, staleness: int = 0) -> Forecast:
        origin = day - 1 - staleness
        hs = [1 + staleness + t for t in range(horizon)]
        arr = self.data[model][series, origin - self.o_min]
        rows = []
        for h in hs:
            if h <= self.h_max and np.isfinite(arr[h - 1, 0]):
                rows.append(arr[h - 1])
            elif rows:
                rows.append(rows[-1])
            else:
                rows.append(np.zeros(len(self.levels) + 1))
        m = np.array(rows)
        return Forecast(
            model=model,
            point=m[:, 0],
            q=m[:, 1:],
            levels=self.levels,
            origin=origin,
            staleness_days=staleness,
        )


@dataclass
class EpisodeResult:
    totals: CostBreakdown
    decisions: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)


def world_supply(
    setup: SeriesSetup, world: WorldScenario, day: int, cfg: dict[str, Any], *, planning_view: bool = False
) -> SupplyContext:
    """Authoritative supplier terms on `day`. With planning_view, master-data changes still hidden by a
    stale-snapshot fault are not applied (what the planning system believes)."""
    sup = base_supply_context(setup.mu, setup.econ, cfg, day)
    if world.disruption("lead_time_increase", day) is not None:
        sup = sup.with_supplier("primary", lead=sup.suppliers[0].lead + 1)
    ev = world.disruption("capacity_reduction", day)
    if ev is not None:
        sup = sup.with_supplier("primary", capacity=sup.suppliers[0].capacity * ev.magnitude)
    if world.disruption("supplier_failure", day) is not None:
        sup = sup.with_supplier("primary", available=False)
    ev = world.disruption("cost_increase", day)
    if ev is not None:
        for nm in ("primary", "alternate"):
            s = next(x for x in sup.suppliers if x.name == nm)
            sup = sup.with_supplier(nm, unit_cost=s.unit_cost * ev.magnitude)
    if world.disruption("transport_disruption", day) is not None:
        sup = sup.with_supplier("expedite", available=False)
        sup = sup.with_supplier("alternate", lead=sup.suppliers[1].lead + 1)
    ev = world.disruption("budget_reduction", day)
    if ev is not None:
        sup = replace(sup, budget=sup.budget * ev.magnitude)
    # Master-data change behind a stale-snapshot fault: real from its start day onward.
    for f in world.faults:
        if f.kind != "stale_supplier_snapshot" or day < f.start:
            continue
        hidden = planning_view and f.active(day)
        if hidden:
            continue
        change = int(f.magnitude)
        if change == 0:
            sup = sup.with_supplier("primary", capacity=sup.suppliers[0].capacity * 0.3)
        elif change == 1:
            sup = sup.with_supplier("alternate", eligible=False)
        else:
            for nm in ("primary", "alternate"):
                s = next(x for x in sup.suppliers if x.name == nm)
                sup = sup.with_supplier(nm, unit_cost=s.unit_cost * 1.3)
    return replace(sup, snapshot_id=f"{'plan' if planning_view else 'auth'}-{setup.series_id}-d{day}")


def cap_to_window(sup: SupplyContext, day: int, last_day: int) -> SupplyContext:
    for s in sup.suppliers:
        if day + s.lead > last_day and s.capacity > 0:
            sup = sup.with_supplier(s.name, capacity=0.0)
    return sup


def demand_multiplier(world: WorldScenario, day: int) -> float:
    m = 1.0
    for kind in ("demand_spike", "demand_collapse"):
        ev = world.disruption(kind, day)
        if ev is not None:
            m *= ev.magnitude
    ev = world.fault("forecast_shift", day)
    if ev is not None:
        m *= ev.magnitude
    return m


def violations(orders: np.ndarray, auth: SupplyContext) -> tuple[list[str], np.ndarray]:
    """Hard-constraint violations under authoritative terms and the quantities that can be delivered."""
    out: list[str] = []
    deliver = orders.copy()
    for i, s in enumerate(auth.suppliers):
        q = orders[i]
        if q <= 1e-9:
            continue
        if not (s.eligible and s.available):
            out.append(f"{s.name}_{'ineligible' if not s.eligible else 'unavailable'}")
            deliver[i] = 0.0
            continue
        if q > s.capacity * (1 + 1e-6) + 1e-9:
            out.append(f"{s.name}_capacity")
            deliver[i] = s.capacity
        if q < s.moq - 1e-6:
            out.append(f"{s.name}_moq")
    if orders @ auth.unit_costs > auth.budget * (1 + 1e-6) + 1e-9:
        out.append("budget")
    return out, deliver


def label_candidate(
    orders: np.ndarray,
    true_cohorts: np.ndarray,
    pipeline: np.ndarray,
    auth: SupplyContext,
    econ: UnitEconomics,
    fc: Forecast,
    mu: float,
    cfg: dict[str, Any],
    key: tuple[Any, ...],
) -> dict[str, Any]:
    """Protocol section 5: unsafe = hard violation, or ex-ante regret under the true state above
    half a day of expected revenue."""
    viol, deliver = violations(orders, auth)
    h = horizon_for(auth.leads, auth.capacities)
    q = fc.q[:h]
    if len(q) < h:
        q = np.vstack([q, np.repeat(q[-1:], h - len(q), axis=0)])
    S = sample_paths(
        q,
        fc.levels,
        int(cfg["benchmark"]["scenarios"]),
        float(cfg["benchmark"]["scenario_day_correlation"]),
        stream(cfg["benchmark"]["seed"], "label", *key),
    )
    grid = action_grid(auth, h)
    pipe = pipeline[:h]
    e_grid = evaluate_actions(true_cohorts, pipe, grid, auth.leads, auth.unit_costs, S, econ).cost.mean(
        axis=1
    )
    e_c = float(
        evaluate_actions(
            true_cohorts, pipe, deliver[None, :], auth.leads, auth.unit_costs, S, econ
        ).cost.mean()
    )
    regret = e_c - float(np.min(e_grid))
    threshold = float(cfg["benchmark"]["unsafe_regret_days_revenue"]) * mu * econ.price
    return {
        "unsafe": bool(viol) or regret > threshold,
        "hard_violation": bool(viol),
        "violations": viol,
        "ex_ante_regret": regret,
        "regret_threshold": threshold,
    }


def _review_costs(
    econ: UnitEconomics, cfg: dict[str, Any], overrides: dict[str, float]
) -> tuple[float, float]:
    e = cfg["economics"]
    inv = float(e["investigation_price_mult"]) * econ.price * overrides.get("investigation_mult", 1.0)
    rev = float(e["review_price_mult"]) * econ.price * overrides.get("review_mult", 1.0)
    return inv, rev


def run_episode(
    setup: SeriesSetup,
    world: WorldScenario,
    spec: PolicySpec,
    store: ForecastStore,
    cfg: dict[str, Any],
    window: tuple[int, int],
    vparams: ValidatorParams,
    overrides: dict[str, float] | None = None,
    keep_samples: int = 0,
) -> EpisodeResult:
    overrides = overrides or {}
    ws, we = window
    econ = setup.econ
    L = econ.shelf_life
    inv = np.zeros(L)
    inv[0] = setup.mu
    pipeline = np.zeros((3, we + 8))  # absolute-day arrivals by supplier
    paid = np.zeros((3, we + 8))  # procurement already charged for those arrivals
    totals = CostBreakdown()
    res = EpisodeResult(totals=totals)
    stockout_hours_y = 0.0
    inv_cost, review_cost = _review_costs(econ, cfg, overrides)
    reviewer_error = float(overrides.get("reviewer_error_rate", cfg["validation"]["reviewer_error_rate"]))
    n_k = int(cfg["benchmark"]["scenarios"])
    rho = float(cfg["benchmark"]["scenario_day_correlation"])
    seed = int(cfg["benchmark"]["seed"])
    cvar_alpha = float(cfg["validation"]["cvar_alpha"])

    for d in range(ws, we + 1):
        auth = cap_to_window(world_supply(setup, world, d, cfg), d, we)
        plan = cap_to_window(world_supply(setup, world, d, cfg, planning_view=True), d, we)
        # 1. receive arrivals; a failed primary does not deliver (payment refunded)
        arrivals = pipeline[:, d].copy()
        if not auth.suppliers[0].available and arrivals[0] > 0:
            totals.procurement -= paid[0, d]
            arrivals[0] = 0.0
        inv[0] += arrivals.sum()
        totals.received_units += float(arrivals.sum())
        true_cohorts = inv.copy()

        # 2. planning snapshot (possibly wrong)
        recorded = true_cohorts.copy()
        jump = 0.0
        f_rec = world.fault("inventory_record_error", d)
        if f_rec is not None:
            phantom = (f_rec.magnitude - 1.0) * 0.6 * setup.mu
            recorded[1 if L > 1 else 0] += phantom
            if d == f_rec.start:
                jump = phantom / setup.mu
        staleness = 2 if world.fault("stale_sales_history", d) is not None else 0
        pipe_view = np.array([0.0] + [pipeline[:, d + o].sum() for o in (1, 2, 3)])
        h_need = 3
        models = {spec.model, "moving_average", "lgbm_point", "lgbm_quantile_recovered"}
        fcs = {m: store.get(m, setup.idx, d, h_need, staleness) for m in models}
        inp = DecisionInputs(
            series_id=setup.series_id,
            day=d,
            last_day=we,
            cohorts=recorded,
            pipeline=pipe_view,
            supply=plan,
            econ=econ,
            mu=setup.mu,
            forecasts=fcs,
            n_scenarios=n_k,
            rho=rho,
            seed=seed,
            data_age_hours=24.0 + 24.0 * staleness,
            history_days_missing=staleness,
        )

        # 3. decide
        t0 = time.perf_counter()
        rec: dict[str, Any] = {
            "series_id": setup.series_id,
            "day": d,
            "policy": spec.pid,
            "condition": world.condition,
            "realization": world.realization,
            "events": "|".join(world.labels()),
            "fault_active": bool(f_rec is not None or staleness or _stale_active(world, d)),
            "outcome": "execute",
            "governance_cost": 0.0,
            "reviewed": False,
        }
        candidate: PolicyDecision
        executed: np.ndarray
        if spec.kind == "oracle":
            realized = np.array(
                [
                    setup.reference[d - 1 + t] * demand_multiplier(world, d + t) if d + t <= we else 0.0
                    for t in range(4)
                ]
            )
            candidate = oracle(true_cohorts, pipe_view, auth, realized, econ, d, we)
            executed = candidate.orders
        elif spec.kind == "base_stock":
            candidate = base_stock(inp, spec.z)
            executed = candidate.orders
        elif spec.kind in ("deterministic", "saa", "cvar"):
            candidate = milp_policy(
                inp,
                spec.pid,
                "lgbm_point" if spec.kind == "deterministic" else spec.model,
                objective="cvar" if spec.kind == "cvar" else "expected",
                alpha=cvar_alpha,
                lam=spec.lam,
                deterministic=spec.kind == "deterministic",
            )
            executed = candidate.orders
        elif spec.kind == "validated":
            candidate, executed, vrec, sample = _validated(
                inp,
                spec,
                auth,
                true_cohorts,
                setup,
                stockout_hours_y,
                jump,
                inv_cost,
                review_cost,
                reviewer_error,
                vparams,
                cfg,
                d,
            )
            rec.update(vrec)
            totals.governance += rec["governance_cost"]
            if sample is not None and len(res.samples) < keep_samples:
                res.samples.append(sample)
        else:
            raise ValueError(spec.kind)
        rec["decision_ms"] = (time.perf_counter() - t0) * 1e3

        # label the candidate (protocol definition: its own forecast) and the executed action (common forecast)
        own_fc = fcs.get(candidate.forecast_model) or fcs["lgbm_quantile_recovered"]
        if spec.kind != "oracle":
            lab = label_candidate(
                candidate.orders,
                true_cohorts,
                pipe_view,
                auth,
                econ,
                own_fc,
                setup.mu,
                cfg,
                (setup.series_id, d, world.condition, world.realization, "own"),
            )
            rec.update({f"cand_{k}": v for k, v in lab.items() if k != "violations"})
            common = (
                fcs["lgbm_quantile_recovered"]
                if staleness == 0
                else store.get("lgbm_quantile_recovered", setup.idx, d, h_need, 0)
            )
            lab2 = label_candidate(
                executed,
                true_cohorts,
                pipe_view,
                auth,
                econ,
                common,
                setup.mu,
                cfg,
                (setup.series_id, d, world.condition, world.realization, "common"),
            )
            rec["exec_unsafe"] = lab2["unsafe"]
            rec["exec_hard_violation"] = lab2["hard_violation"]
            rec["exec_regret"] = lab2["ex_ante_regret"]

        # 4. execute against authoritative terms
        viol, deliver = violations(executed, auth)
        spend = float(executed @ auth.unit_costs)
        total_q = float(executed.sum())
        standard_usable = bool((auth.capacities[:2] > 1e-9).any())
        needs_approval = spend > auth.approval_threshold + 1e-9 or (
            standard_usable and total_q > 1e-9 and executed[2] / total_q > auth.max_expedite_share + 1e-9
        )
        if needs_approval and not rec["reviewed"]:
            totals.governance += review_cost
            rec["governance_cost"] += review_cost
            rec["approval_review"] = True
        charge = deliver * auth.unit_costs
        totals.procurement += float(charge.sum())
        for s in (0, 1):
            if deliver[s] > 0:
                arr_day = d + int(auth.suppliers[s].lead)
                pipeline[s, arr_day] += deliver[s]
                paid[s, arr_day] += charge[s]
        totals.received_units += float(deliver[2])

        # 5. demand and the day's operations
        demand = float(setup.reference[d - 1] * demand_multiplier(world, d))
        out = step(inv[None, :], np.array([deliver[2]]), np.array([demand]), econ)  # mutates inv in place
        dc = day_costs(out, econ, demand, 0.0)
        totals.add(dc)
        stockout_hours_y = (
            SHELF_HOURS * float(out["lost"][0]) / demand if demand > 0 and out["lost"][0] > 1e-9 else 0.0
        )
        rec.update(
            {
                "orders_candidate": [round(float(x), 4) for x in candidate.orders],
                "orders_executed": [round(float(x), 4) for x in executed],
                "violations": "|".join(viol),
                "n_violations": len(viol),
                "spend": spend,
                "demand": demand,
                "sales": float(out["sales"][0]),
                "lost": float(out["lost"][0]),
                "waste": float(out["waste"][0]),
                "end_units": float(out["end_units"][0]),
                "day_cost": dc.total + float(charge.sum()) + rec["governance_cost"],
                "status": candidate.status,
            }
        )
        res.decisions.append(rec)

    # terminal valuation of stock left at the end of the window (identical rule for every policy)
    totals.terminal_adjustment += econ.terminal_charge * float(inv.sum())
    return res


def _stale_active(world: WorldScenario, d: int) -> bool:
    return world.fault("stale_supplier_snapshot", d) is not None


def _validated(
    inp: DecisionInputs,
    spec: PolicySpec,
    auth: SupplyContext,
    true_cohorts: np.ndarray,
    setup: SeriesSetup,
    stockout_hours_y: float,
    jump: float,
    inv_cost: float,
    review_cost: float,
    reviewer_error: float,
    vparams: ValidatorParams,
    cfg: dict[str, Any],
    d: int,
) -> tuple[PolicyDecision, np.ndarray, dict[str, Any], dict[str, Any] | None]:
    alpha = vparams.cvar_alpha
    obj = "cvar" if spec.wrapped == "cvar" else "expected"
    base = milp_policy(inp, spec.pid, spec.model, objective=obj, alpha=alpha, lam=spec.lam)
    fc = inp.forecasts[spec.model]
    h = base.horizon
    decision_id = re.sub(
        r"[^A-Za-z0-9_.:\-]", "_", f"{setup.series_id}.d{d}.{inp.supply.snapshot_id}.{spec.pid}"
    )
    cand = build_candidate(
        decision_id=decision_id[:120],
        day=d,
        decision_time=f"day-{d}T06:00",
        series_id=setup.series_id,
        category=setup.profile,
        mu=setup.mu,
        orders=base.orders,
        snapshot_supply=inp.supply,
        econ=setup.econ,
        cohorts=inp.cohorts,
        pipeline=inp.pipeline[:4],
        forecast_q=fc.q[:h],
        levels=fc.levels,
        model_version=spec.model,
        policy_version=f"{spec.wrapped}-milp-1.0",
        objective=obj,
        expected_cost=base.expected_cost,
        cvar_value=base.cvar,
        n_scenarios=inp.n_scenarios,
        age_hours=inp.data_age_hours,
        history_days_missing=inp.history_days_missing,
        snapshot_id=inp.supply.snapshot_id,
        alpha=alpha,
        lam=spec.lam if obj == "cvar" else None,
    )
    ctx = AuthoritativeContext(
        constraints=constraints_from(auth),
        financial_assumptions=assumptions_from(setup.econ),
        approval_threshold=auth.approval_threshold,
        max_share={"expedite": auth.max_expedite_share},
        freshness_max_age_hours=float(cfg["validation"]["freshness_max_age_hours"]),
        signals={"stockout_hours_yesterday": stockout_hours_y, "record_jump_ratio": jump},
        investigation_cost=inv_cost,
        review_cost=review_cost,
    )
    rep = validate(cand, ctx, ADAPTER, vparams)
    outcome = rep.outcome
    gov = 0.0
    reviewed = False
    executed = base.orders
    note = ""
    true_inp = replace(inp, cohorts=true_cohorts)
    if outcome == "reject":
        executed = milp_policy(
            inp, spec.pid, spec.model, objective=obj, alpha=alpha, lam=spec.lam, supply=auth
        ).orders
    elif outcome == "investigate" and spec.use_voi:
        gov += inv_cost
        executed = milp_policy(
            true_inp, spec.pid, spec.model, objective=obj, alpha=alpha, lam=spec.lam
        ).orders
    elif outcome == "defer":
        executed = np.zeros(3)
    elif outcome in ("escalate", "investigate"):
        if spec.use_escalation:
            gov += review_cost
            reviewed = True
            if stream(vparams.seed, "reviewer", decision_id).random() < reviewer_error:
                note = "reviewer approved the original candidate"
            else:
                executed = milp_policy(
                    true_inp,
                    spec.pid,
                    spec.model,
                    objective="cvar" if spec.risk_review else "expected",
                    alpha=alpha,
                    lam=0.5,
                    supply=auth,
                ).orders
        elif rep.recommended_action is not None:
            executed = np.array([rep.recommended_action[n] for n in ("primary", "alternate", "expedite")])
    g = {x.gate: x for x in rep.gates}
    vrec = {
        "outcome": outcome,
        "governance_cost": gov,
        "reviewed": reviewed,
        "reviewer_note": note,
        **{f"{k}_status": g[k].status for k in g},
        "evpi": rep.metrics.get("evpi"),
        "value_vs_candidate": rep.metrics.get("value_vs_candidate"),
        "claim_gap": rep.metrics.get("claim_gap"),
        "tail_gain": rep.metrics.get("tail_gain"),
        "stress_gain": rep.metrics.get("stress_gain"),
        "revenue_scale": rep.metrics.get("revenue_scale"),
        "financial_rel_diff": rep.metrics.get("financial_relative_difference"),
        "anomaly": bool(g["G1"].evidence.get("flag", False)),
        "approval_required": bool(g["G7"].evidence.get("approval_required", False)),
        "investigation_cost": inv_cost,
    }
    sample = {
        "candidate": cand.model_dump(),
        "context": ctx.model_dump(),
        "report_outcome": outcome,
        "true_on_hand_by_age": [float(x) for x in true_cohorts],
    }
    return base, executed, vrec, sample


def make_setup(panel: Any, idx: int, reference: np.ndarray, cfg: dict[str, Any], fit_end: int) -> SeriesSetup:
    profile = panel.profile[idx]
    econ = economics_for(profile, cfg)
    hist = panel.sales[idx, 28:fit_end]
    mu = float(np.nanmean(hist)) if np.isfinite(hist).any() else 1.0
    return SeriesSetup(
        idx=idx,
        series_id=panel.series_ids[idx],
        profile=profile,
        econ=econ,
        mu=max(mu, 0.5),
        reference=reference[idx],
    )
