"""Secondary domain: weekly cloud compute capacity reservation (synthetic, reproducible).

A platform team sets, for each service and week, a reserved capacity commitment R (vCPU, paid for
every day of the week), a spot request ceiling S (interruptible, usage-priced, batch work only) and an
on-demand ceiling O (usage-priced, bounded by the provider quota). Time-sensitive work may use only
reserved or on-demand capacity; unserved time-sensitive work incurs an SLA penalty, unserved batch
work a smaller delay penalty.

Reused from the core framework without modification: the DecisionCandidate contract, the validation
engine and its seven gates, VOI, CVaR, the cluster bootstrap and the detection metrics. Domain-specific:
the cost model, the demand generator and forecast, stress cases, anomaly signals and the candidate grid.
All data here is synthetic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from edi.benchmark.report import detection, paired
from edi.benchmark.stats import bootstrap_mean
from edi.core import artifact_path, utc_now, write_json
from edi.simulation.engine import cvar
from edi.simulation.scenarios import sample_paths, stream
from edi.validation.engine import ValidatorParams, validate
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
)

DAYS = 7
LEVELS = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95]
NAMES = ("reserved", "spot", "on_demand")


@dataclass(frozen=True)
class CloudPrices:
    reserved: float = 0.60  # per vCPU-day, committed
    on_demand: float = 1.00  # per vCPU-day used
    spot: float = 0.30  # per vCPU-day used
    sla_penalty: float = 4.0  # per unserved time-sensitive vCPU-day
    delay_penalty: float = 0.5  # per unserved batch vCPU-day


def costs(
    actions: np.ndarray,
    demand: np.ndarray,
    spot_avail: np.ndarray,
    ts_share: float,
    prices: CloudPrices,
    reserved_price: float | None = None,
) -> np.ndarray:
    """(A, 3) actions x (K, 7) demand -> (A, K) weekly cost."""
    a = np.atleast_2d(actions)[:, :, None, None]
    R, S, od = a[:, 0], a[:, 1], a[:, 2]
    D = demand[None, :, :]
    ts, batch = ts_share * D, (1 - ts_share) * D
    ts_res = np.minimum(ts, R)
    rem = R - ts_res
    ts_od = np.minimum(ts - ts_res, od)
    un_ts = ts - ts_res - ts_od
    b_res = np.minimum(batch, rem)
    b_spot = np.minimum(batch - b_res, S * spot_avail[None, :, :])
    b_od = np.minimum(batch - b_res - b_spot, od - ts_od)
    un_b = batch - b_res - b_spot - b_od
    pr = prices.reserved if reserved_price is None else reserved_price
    daily = (
        (ts_od + b_od) * prices.on_demand
        + b_spot * prices.spot
        + un_ts * prices.sla_penalty
        + un_b * prices.delay_penalty
    )
    return (DAYS * pr * np.atleast_2d(actions)[:, 0])[:, None] + daily.sum(axis=2)


def grid_for(mu: float, quota_od: float, quota_res: float, budget: float, price_r: float) -> np.ndarray:
    R = np.linspace(0, min(quota_res, 2.0 * mu), 15)
    S = np.linspace(0, 1.5 * mu, 5)
    od = np.linspace(0, quota_od, 4)
    g = np.array(np.meshgrid(R, S, od, indexing="ij")).reshape(3, -1).T
    return g[DAYS * price_r * g[:, 0] <= budget + 1e-9]


@dataclass
class Service:
    sid: str
    mu: float
    ts_share: float
    growth: float
    weekly: np.ndarray
    launch_week: int


def make_services(n: int, seed: int) -> list[Service]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        weekly = 1 + rng.uniform(0.05, 0.3) * np.array([0.2, 0.3, 0.3, 0.2, 0.0, -0.6, -0.4])
        out.append(
            Service(
                f"svc{i:03d}",
                float(rng.lognormal(np.log(120), 0.6)),
                float(rng.uniform(0.4, 0.85)),
                float(rng.normal(0.01, 0.02)),
                weekly,
                int(rng.integers(6, 12)) if rng.random() < 0.35 else -1,
            )
        )
    return out


def demand_path(svc: Service, week: int, rng: np.random.Generator) -> np.ndarray:
    lvl = svc.mu * (1 + svc.growth) ** week
    launch = 1.35 if svc.launch_week >= 0 and week >= svc.launch_week else 1.0
    return np.maximum(
        lvl * launch * svc.weekly * rng.lognormal(0, 0.12, DAYS) * np.exp(rng.normal(0, 0.08)), 0
    )


def forecast_quantiles(history: list[np.ndarray]) -> np.ndarray:
    """Trailing four-week mean by weekday with empirical relative residual quantiles (no future data)."""
    h = np.array(history[-4:])
    point = h.mean(axis=0)
    rel = (h / np.maximum(point, 1e-9) - 1).ravel()
    spread = (
        np.quantile(rel, LEVELS) if len(rel) > 6 else np.array([-0.25, -0.18, -0.08, 0, 0.08, 0.18, 0.25])
    )
    spread = np.maximum.accumulate(spread * 1.3)
    return np.maximum(point[:, None] * (1 + spread[None, :]), 0)


class CloudAdapter:
    name = "cloud_capacity"

    def __init__(self, prices: CloudPrices):
        self.prices = prices

    def required_state(self) -> list[str]:
        return ["utilization_last_week"]

    def revenue_scale(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> float:
        return float(cand.entity.typical_daily_volume * self.prices.on_demand)

    def scenarios(self, cand: DecisionCandidate, k: int, rho: float, rng: np.random.Generator) -> np.ndarray:
        assert cand.forecast is not None
        return sample_paths(np.array(cand.forecast.quantiles), cand.forecast.levels, k, rho, rng)

    def _terms(
        self, cand: DecisionCandidate, ctx: AuthoritativeContext, terms: str
    ) -> tuple[Constraints, float, float]:
        c = cand.constraints if terms == "candidate" else ctx.constraints
        by = {r.name: r for r in c.resources}
        return c, by["reserved"].unit_cost / DAYS, float(by["spot"].attributes.get("availability", 0.85))

    def evaluate(self, cand, ctx, actions, scenarios, state=None, terms="authoritative") -> np.ndarray:
        c, price_r, avail = self._terms(cand, ctx, terms)
        by = {r.name: r for r in c.resources}
        caps = np.array([by[n].capacity if (by[n].eligible and by[n].available) else 0.0 for n in NAMES])
        acts = np.minimum(np.atleast_2d(actions), caps[None, :])
        uplift = float((state or {}).get("demand_uplift", 1.0))
        spot = np.full(scenarios.shape, avail)
        ts = float(by["reserved"].attributes.get("ts_share", 0.6))
        return costs(acts, scenarios * uplift, spot, ts, self.prices, reserved_price=price_r)

    def grid(self, cand, ctx) -> np.ndarray:
        by = {r.name: r for r in ctx.constraints.resources}
        return grid_for(
            cand.entity.typical_daily_volume,
            by["on_demand"].capacity,
            by["reserved"].capacity,
            ctx.constraints.budget,
            by["reserved"].unit_cost / DAYS,
        )

    def stress_cases(self, cand, ctx, scenarios):
        def spot_crunch(acts):
            c2 = ctx.model_copy(deep=True)
            for r in c2.constraints.resources:
                if r.name == "spot":
                    r.attributes["availability"] = 0.2
            return self.evaluate(cand, c2, acts, scenarios)

        return [
            ("spot capacity mostly reclaimed", spot_crunch),
            ("demand 40% above forecast", lambda acts: self.evaluate(cand, ctx, acts, scenarios * 1.4)),
            ("demand 40% below forecast", lambda acts: self.evaluate(cand, ctx, acts, scenarios * 0.6)),
        ]

    def anomaly(self, cand, ctx, params):
        p = float(ctx.signals.get("launch_probability", 0.0))
        if 0.15 <= p <= 0.85:
            return {
                "flag": True,
                "reasons": [f"a product launch this week is unconfirmed (probability {p:.0%})"],
                "input": "launch timing",
                "launch_probability": p,
            }
        return {"flag": False, "reasons": [], "input": "launch timing"}

    def state_hypotheses(self, cand, params, anomalous):
        p = float(cand.data_snapshot.state.get("launch_probability", [0.0])[0])
        return [
            ("no launch", 1 - p, {"demand_uplift": 1.0}),
            ("launch goes ahead", p, {"demand_uplift": 1.35}),
        ]


def _resources(
    mu: float,
    quota_res: float,
    quota_od: float,
    price_r: float,
    avail: float,
    ts: float,
    spot_ok: bool = True,
) -> list[Resource]:
    return [
        Resource(
            name="reserved",
            lead_days=0,
            unit_cost=DAYS * price_r,
            capacity=quota_res,
            min_quantity=0.0,
            attributes={"committed": True, "ts_share": ts},
        ),
        Resource(
            name="spot",
            lead_days=0,
            unit_cost=0.30,
            capacity=1.5 * mu,
            eligible=spot_ok,
            attributes={"committed": False, "availability": avail},
        ),
        Resource(
            name="on_demand", lead_days=0, unit_cost=1.0, capacity=quota_od, attributes={"committed": False}
        ),
    ]


def run_experiment(
    cfg: dict[str, Any], n_services: int = 40, weeks: tuple[int, int] = (8, 13)
) -> dict[str, Any]:
    t0 = time.perf_counter()
    prices = CloudPrices()
    adapter = CloudAdapter(prices)
    vparams = ValidatorParams.from_config(cfg)
    seed = int(cfg["benchmark"]["seed"])
    services = make_services(n_services, seed)
    K = 120
    rows, decs = [], []
    for svc in services:
        hist_rng = stream(seed, "cloud-hist", svc.sid)
        history = [demand_path(svc, w, hist_rng) for w in range(weeks[0])]
        for w in range(*weeks):
            for cond in ("normal", "unreliable", "disruption"):
                wr = stream(seed, "cloud-world", svc.sid, w, cond)
                actual = demand_path(svc, w, stream(seed, "cloud-demand", svc.sid, w))
                launch_p = 0.0
                launch_happens = False
                quota_res, quota_od, price_r, avail, age = (
                    2.0 * svc.mu,
                    1.2 * svc.mu,
                    prices.reserved,
                    0.85,
                    12.0,
                )
                plan = dict(quota_res=quota_res, quota_od=quota_od, price_r=price_r, avail=avail)
                auth = dict(plan)
                fault = "none"
                if cond == "unreliable":
                    fault = ["stale_telemetry", "stale_quota", "stale_price", "launch_unconfirmed"][
                        int(wr.integers(4))
                    ]
                    if fault == "stale_telemetry":
                        age = 96.0
                    elif fault == "stale_quota":
                        auth["quota_od"] = 0.4 * svc.mu
                    elif fault == "stale_price":
                        auth["price_r"] = price_r * 1.25
                    else:
                        launch_p = 0.5
                        launch_happens = bool(wr.random() < 0.5)
                        if launch_happens:
                            actual = actual * 1.35
                elif cond == "disruption":
                    fault = ["spot_crunch", "demand_spike", "quota_cut"][int(wr.integers(3))]
                    if fault == "spot_crunch":
                        auth["avail"] = plan["avail"] = 0.2
                    elif fault == "demand_spike":
                        actual = actual * 1.4
                    else:
                        auth["quota_od"] = plan["quota_od"] = 0.5 * svc.mu
                fq = forecast_quantiles(history if fault != "stale_telemetry" else history[:-1])
                budget = DAYS * prices.reserved * 1.6 * svc.mu
                plan_c = Constraints(
                    resources=_resources(
                        svc.mu,
                        plan["quota_res"],
                        plan["quota_od"],
                        plan["price_r"],
                        plan["avail"],
                        svc.ts_share,
                    ),
                    budget=budget,
                )
                auth_c = Constraints(
                    resources=_resources(
                        svc.mu,
                        auth["quota_res"],
                        auth["quota_od"],
                        auth["price_r"],
                        auth["avail"],
                        svc.ts_share,
                    ),
                    budget=budget,
                )
                S = sample_paths(fq, LEVELS, K, 0.6, stream(seed, "cloud-policy", svc.sid, w, cond))
                spot_plan = np.full(S.shape, plan["avail"])
                g = grid_for(svc.mu, plan["quota_od"], plan["quota_res"], budget, plan["price_r"])
                C = costs(g, S, spot_plan, svc.ts_share, prices, reserved_price=plan["price_r"])
                e, cv = C.mean(axis=1), cvar(C, 0.9)
                med = fq[:, LEVELS.index(0.5)]
                policies = {
                    "C1_reserve_mean": np.array(
                        [svc.ts_share * med.mean(), 0.6 * (1 - svc.ts_share) * med.mean(), plan["quota_od"]]
                    ),
                    "C2_deterministic": g[
                        int(
                            np.argmin(
                                costs(
                                    g,
                                    med[None, :],
                                    np.full((1, DAYS), plan["avail"]),
                                    svc.ts_share,
                                    prices,
                                    plan["price_r"],
                                )[:, 0]
                            )
                        )
                    ],
                    "C3_expected": g[int(np.argmin(e))],
                    "C4_cvar": g[int(np.argmin(0.5 * e + 0.5 * cv))],
                }
                for pid, act in list(policies.items()) + [("C5_validated", policies["C3_expected"])]:
                    gov = 0.0
                    outcome = "execute"
                    executed = act
                    cand = DecisionCandidate(
                        decision_id=f"{svc.sid}.w{w}.{cond}.{pid}",
                        domain="cloud_capacity",
                        decision_day=w * 7,
                        decision_time=f"week-{w}",
                        entity=Entity(entity_id=svc.sid, category="compute", typical_daily_volume=svc.mu),
                        data_snapshot=DataSnapshot(
                            snapshot_id=f"plan-{svc.sid}-w{w}",
                            as_of=f"week-{w}",
                            age_hours=age,
                            history_days_missing=7 if fault == "stale_telemetry" else 0,
                            state={
                                "utilization_last_week": [float(x) for x in history[-1]],
                                "launch_probability": [launch_p],
                            },
                        ),
                        action={n: float(v) for n, v in zip(NAMES, act)},
                        objective=Objective(type="expected"),
                        constraints=plan_c,
                        forecast=ForecastDistribution(
                            model_version="trailing-4w", levels=LEVELS, quantiles=fq.tolist()
                        ),
                        financial_assumptions=FinancialAssumptions(
                            price=prices.on_demand,
                            unit_cost=plan["price_r"],
                            holding=0,
                            disposal=0,
                            goodwill=prices.sla_penalty,
                            shelf_life_days=7,
                            terminal_waste_risk=0,
                        ),
                        scenario_results=ScenarioResults(
                            expected_cost=float(
                                costs(
                                    act[None, :], S, spot_plan, svc.ts_share, prices, plan["price_r"]
                                ).mean()
                            ),
                            n_scenarios=K,
                        ),
                        model_version="trailing-4w",
                        policy_version=pid,
                    )
                    ctx = AuthoritativeContext(
                        constraints=auth_c,
                        financial_assumptions=cand.financial_assumptions.model_copy(
                            update={"unit_cost": auth["price_r"]}
                        ),
                        approval_threshold=DAYS * prices.reserved * 1.3 * svc.mu,
                        freshness_max_age_hours=48,
                        signals={"launch_probability": launch_p},
                        investigation_cost=0.3 * svc.mu * prices.on_demand * 0.1,
                        review_cost=0.3 * svc.mu * prices.on_demand * 0.25,
                    )
                    rep = validate(cand, ctx, adapter, vparams)
                    if pid == "C5_validated":
                        outcome = rep.outcome
                        if outcome == "reject" and rep.recommended_action:
                            executed = np.array([rep.recommended_action[n] for n in NAMES])
                        elif outcome == "investigate":
                            gov += ctx.investigation_cost
                            uplift = (
                                1.35 if launch_happens else 1.0
                            )  # confirmation reveals the launch decision
                            C2 = costs(g, S * uplift, spot_plan, svc.ts_share, prices, plan["price_r"])
                            executed = g[int(np.argmin(C2.mean(axis=1)))]
                        elif outcome in ("escalate", "defer"):
                            gov += ctx.review_cost
                            ag = adapter.grid(cand, ctx)
                            Ca = adapter.evaluate(cand, ctx, ag, S)
                            executed = ag[int(np.argmin(0.5 * Ca.mean(axis=1) + 0.5 * cvar(Ca, 0.9)))]
                    # realized outcome under authoritative terms
                    by = {r.name: r for r in auth_c.resources}
                    hard = []
                    if executed[0] > by["reserved"].capacity + 1e-6:
                        hard.append("reserved_quota")
                    if executed[2] > by["on_demand"].capacity + 1e-6:
                        hard.append("on_demand_quota")
                    if DAYS * auth["price_r"] * executed[0] > budget + 1e-6:
                        hard.append("budget")
                    caps = np.array([by[n].capacity for n in NAMES])
                    real = (
                        float(
                            costs(
                                np.minimum(executed, caps)[None, :],
                                actual[None, :],
                                np.full((1, DAYS), auth["avail"]),
                                svc.ts_share,
                                prices,
                                auth["price_r"],
                            )[0, 0]
                        )
                        + gov
                    )
                    if (executed[0] * DAYS * auth["price_r"] > ctx.approval_threshold) and outcome not in (
                        "escalate",
                        "defer",
                    ):
                        real += ctx.review_cost
                        gov += ctx.review_cost
                    # unsafe label of the candidate (protocol definition, true terms, own forecast)
                    ag = adapter.grid(cand, ctx)
                    S_l = sample_paths(fq, LEVELS, K, 0.6, stream(seed, "cloud-label", svc.sid, w, cond))
                    true_state = {"demand_uplift": 1.35 if launch_happens else 1.0}
                    e_best = np.min(adapter.evaluate(cand, ctx, ag, S_l, state=true_state).mean(axis=1))
                    e_c = float(adapter.evaluate(cand, ctx, act[None, :], S_l, state=true_state).mean())
                    unsafe_hard = bool(
                        act[0] > by["reserved"].capacity + 1e-6
                        or act[2] > by["on_demand"].capacity + 1e-6
                        or DAYS * auth["price_r"] * act[0] > budget + 1e-6
                    )
                    unsafe = unsafe_hard or (e_c - e_best) > 0.5 * svc.mu * prices.on_demand
                    rows.append(
                        {
                            "series_id": svc.sid,
                            "realization": w,
                            "condition": cond,
                            "policy": pid,
                            "total": real,
                            "n_days": DAYS,
                            "governance": gov,
                            "event": fault,
                        }
                    )
                    decs.append(
                        {
                            "policy": pid,
                            "condition": cond,
                            "outcome": rep.outcome if pid == "C5_validated" else outcome,
                            "cand_unsafe": unsafe,
                            "events": fault,
                            "hard": bool(hard),
                        }
                    )
            history.append(demand_path(svc, w, stream(seed, "cloud-demand", svc.sid, w)))
    tot = pd.DataFrame(rows)
    dec = pd.DataFrame(decs)
    B = int(cfg["benchmark"]["bootstrap_resamples"])
    res: dict[str, Any] = {
        "meta": {
            "run_name": cfg["run_name"],
            "data_source": "synthetic",
            "n_services": n_services,
            "weeks": list(weeks),
            "generated_at": utc_now(),
            "prices": prices.__dict__,
            "note": "Synthetic cloud capacity scenario. Costs are illustrative.",
        },
        "results": {},
        "paired": {},
        "detection": {},
    }
    for cond in ("normal", "unreliable", "disruption"):
        t = tot[tot["condition"] == cond]
        res["results"][cond] = {}
        for p in sorted(t["policy"].unique()):
            g = t[t["policy"] == p].assign(cost_per_day=lambda x: x["total"] / x["n_days"])
            per = g.groupby("series_id")["cost_per_day"].mean()
            res["results"][cond][p] = {
                "cost_per_service_day": bootstrap_mean(per.to_numpy(), B, seed),
                "cvar90": float(cvar(g["cost_per_day"].to_numpy(), 0.9)),
                "hard_violations": int(dec[(dec["condition"] == cond) & (dec["policy"] == p)]["hard"].sum()),
            }
        res["paired"][cond] = {
            "C5_vs_C3": paired(t, "C5_validated", "C3_expected", B, seed),
            "C4_vs_C3": paired(t, "C4_cvar", "C3_expected", B, seed),
            "C3_vs_C1": paired(t, "C3_expected", "C1_reserve_mean", B, seed),
        }
        d = dec[(dec["condition"] == cond) & (dec["policy"] == "C5_validated")]
        res["detection"][cond] = detection(d.assign(events=d["events"]))
    res["reuse"] = {
        "reused_unchanged": [
            "DecisionCandidate schema v1.0",
            "validation engine and gates G1-G7",
            "EVPI and value of verification",
            "CVaR",
            "cluster bootstrap",
            "paired comparison",
            "detection metrics",
        ],
        "domain_specific": [
            "cost model (reserved, spot, on-demand, SLA and delay penalties)",
            "demand generator and trailing forecast",
            "candidate grid",
            "stress cases",
            "anomaly signal (unconfirmed launch)",
            "policies C1-C5",
        ],
        "engine_change_needed": "one generalization: spend counts only resources marked committed (usage-priced limits excluded)",
    }
    res["meta"]["runtime_seconds"] = round(time.perf_counter() - t0, 1)
    path = artifact_path(cfg, "benchmark", "secondary_cloud.json")
    write_json(path, res)
    return {"path": str(path), "runtime_seconds": res["meta"]["runtime_seconds"], **res}
