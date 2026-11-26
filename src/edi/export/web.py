"""Export compact, versioned JSON for the static web application, plus golden fixtures that pin the
browser engine to this Python reference.

`studio_evaluate` is the reference implementation of every number the browser recomputes when a user
changes assumptions. The TypeScript port in apps/web/src/engine must reproduce it on the fixtures.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from edi.benchmark.report import latest_run
from edi.benchmark.runner import ForecastStore
from edi.core import config_hash, git_sha, read_json, repo_path, utc_now, write_json
from edi.finance.economics import SupplyContext, UnitEconomics
from edi.forecasting.run import load_forecasts
from edi.optimization.milp import action_grid
from edi.pipeline import layout, load_panel
from edi.simulation.engine import cvar, evaluate_actions, horizon_for
from edi.simulation.scenarios import quantile_function, sample_paths, stream
from edi.validation.engine import ValidatorParams, validate
from edi.validation.inaction import alternatives
from edi.validation.inventory import (
    InventoryAdapter,
    assumptions_from,
    build_candidate,
    constraints_from,
    econ_from,
    supply_from,
)
from edi.validation.schema import AuthoritativeContext, DecisionCandidate

WEB_DATA = repo_path("apps", "web", "public", "data")
FIXTURES = repo_path("apps", "web", "src", "engine", "__fixtures__")
GRID_SHAPE = (12, 6, 5)
CASE_SCENARIOS_MAX = 400
ADAPTER = InventoryAdapter()


def r(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


def validator_params(cfg: dict[str, Any], soft_scale: float, n_scenarios: int) -> ValidatorParams:
    vp = ValidatorParams.from_config(cfg)
    return replace(
        vp,
        loss_tolerance_mult=vp.loss_tolerance_mult * soft_scale,
        stress_tolerance_mult=vp.stress_tolerance_mult * soft_scale,
        n_scenarios=n_scenarios,
    )


def params_dict(vp: ValidatorParams) -> dict[str, Any]:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in vp.__dict__.items()}


# ------------------------------------------------------------------ studio reference


def _econ(case: dict[str, Any]) -> UnitEconomics:
    e = case["economics"]
    return UnitEconomics(
        e["price"],
        e["unit_cost"],
        e["shelf_life"],
        e["holding"],
        e["disposal"],
        e["goodwill"],
        e["terminal_waste_risk"],
    )


def _supply(case: dict[str, Any], mods: dict[str, Any]) -> SupplyContext:
    t = case["current_terms"]
    sup = supply_from(constraints_from_dict(t))
    sup = replace(
        sup,
        budget=t["budget"] * float(mods.get("budget_mult", 1.0)),
        approval_threshold=case["approval_threshold"],
        max_expedite_share=case["max_expedite_share"],
    )
    delay = int(mods.get("primary_delay_days", 0))
    if delay:
        sup = sup.with_supplier("primary", lead=sup.suppliers[0].lead + delay)
    cc = float(mods.get("cost_change", 0.0))
    if cc:
        for s in sup.suppliers:
            sup = sup.with_supplier(s.name, unit_cost=s.unit_cost * (1.0 + cc))
    if not mods.get("primary_available", True):
        sup = sup.with_supplier("primary", available=False)
    if not mods.get("alternate_eligible", True):
        sup = sup.with_supplier("alternate", eligible=False)
    if not mods.get("expedite_available", True):
        sup = sup.with_supplier("expedite", available=False)
    return sup


def constraints_from_dict(t: dict[str, Any]):  # noqa: ANN201
    from edi.validation.schema import Constraints

    return Constraints.model_validate(
        {"resources": t["resources"], "budget": t["budget"], "min_commitment": t.get("min_commitment", 0.0)}
    )


def studio_evaluate(case: dict[str, Any], mods: dict[str, Any], vp: ValidatorParams) -> dict[str, Any]:
    econ = _econ(case)
    sup = _supply(case, mods)
    cohorts = np.array(
        case["state"]["verified_on_hand_by_age" if mods.get("use_verified") else "recorded_on_hand_by_age"]
    )
    pipeline = np.array(case["state"]["pipeline_by_day"])
    S3 = np.array(case["scenarios"]) * (1.0 + float(mods.get("demand_shift", 0.0)))
    h = int(min(3, horizon_for(sup.leads, sup.capacities)))
    S = S3[:, :h]
    lam = float(mods.get("risk_weight", 0.5))
    alpha = float(mods.get("alpha", 0.9))
    grid = action_grid(sup, h, *GRID_SHAPE)
    pipe = np.zeros(h)
    pipe[: min(h, len(pipeline))] = pipeline[:h]
    C = evaluate_actions(cohorts, pipe, grid, sup.leads, sup.unit_costs, S, econ).cost
    E = C.mean(axis=1)
    CV = cvar(C, alpha)
    score = (1 - lam) * E + lam * CV
    ib, ir = int(np.argmin(E)), int(np.argmin(score))
    orig = np.minimum(np.array(case["candidate"]["orders"]), sup.capacities)
    Co = evaluate_actions(cohorts, pipe, orig[None, :], sup.leads, sup.unit_costs, S, econ).cost[0]
    rec = grid[ir]
    # validate the recommended action under the modified, authoritative world
    fq = np.array(case["forecast"]["quantiles"])[:h] * (1.0 + float(mods.get("demand_shift", 0.0)))
    cand = build_candidate(
        decision_id=f"studio.{case['id']}",
        day=case["day"],
        decision_time=case["date"],
        series_id=case["entity"]["series_id"],
        category=case["entity"]["category"],
        mu=case["mu"],
        orders=rec,
        snapshot_supply=sup,
        econ=econ,
        cohorts=cohorts,
        pipeline=pipeline,
        forecast_q=fq,
        levels=case["forecast"]["levels"],
        model_version="studio",
        policy_version="studio-grid",
        objective="cvar" if lam > 0 else "expected",
        expected_cost=float(E[ir]),
        cvar_value=float(CV[ir]),
        n_scenarios=S.shape[0],
        age_hours=24.0,
        history_days_missing=0,
        snapshot_id=f"studio-{case['id']}",
        alpha=alpha,
    )
    ctx = context_for(case, sup, econ, case["signals"] if not mods.get("use_verified") else {})
    rep = validate(cand, ctx, ADAPTER, vp, scenarios=S)
    alts = alternatives(
        rec,
        cohorts,
        pipeline,
        sup,
        econ,
        S,
        case["review_cost"],
        alpha,
        tolerance_margin=case["revenue_scale"],
    )
    # risk-adjusted cost surface (the objective being minimized) over primary x alternate at the
    # recommended expedite level
    pri = np.unique(grid[:, 0])
    alt = np.unique(grid[:, 1])
    surf = np.full((len(pri), len(alt)), np.nan)
    sel = np.isclose(grid[:, 2], rec[2])
    for k in np.where(sel)[0]:
        surf[np.searchsorted(pri, grid[k, 0]), np.searchsorted(alt, grid[k, 1])] = score[k]
    return {
        "horizon": h,
        "grid_size": int(len(grid)),
        "best_expected": {"orders": [r(x) for x in grid[ib]], "expected": r(E[ib]), "cvar": r(CV[ib])},
        "recommended": {
            "orders": [r(x) for x in rec],
            "expected": r(E[ir]),
            "cvar": r(CV[ir]),
            "score": r(score[ir]),
        },
        "original": {
            "orders": [r(x) for x in orig],
            "expected": r(Co.mean()),
            "cvar": r(float(cvar(Co, alpha))),
            "score": r((1 - lam) * Co.mean() + lam * float(cvar(Co, alpha))),
        },
        "validation": report_dict(rep),
        "alternatives": [
            {
                **a,
                **{k: r(v) for k, v in a.items() if isinstance(v, float)},
                "orders": [r(x) for x in a["orders"]],
            }
            for a in alts
        ],
        "surface": {
            "primary": [r(x) for x in pri],
            "alternate": [r(x) for x in alt],
            "value": [[None if not np.isfinite(v) else r(v) for v in row] for row in surf],
            "measure": "risk_adjusted" if lam > 0 else "expected",
        },
    }


def context_for(
    case: dict[str, Any], sup: SupplyContext, econ: UnitEconomics, signals: dict[str, float]
) -> AuthoritativeContext:
    return AuthoritativeContext(
        constraints=constraints_from(sup),
        financial_assumptions=assumptions_from(econ),
        approval_threshold=sup.approval_threshold,
        max_share={"expedite": sup.max_expedite_share},
        freshness_max_age_hours=case["freshness_max_age_hours"],
        signals=signals,
        investigation_cost=case["investigation_cost"],
        review_cost=case["review_cost"],
    )


def report_dict(rep: Any) -> dict[str, Any]:
    d = rep.model_dump()
    return {
        "outcome": d["outcome"],
        "reasons": d["reasons"],
        "explanation": d["explanation"],
        "recommended_action": d["recommended_action"],
        "metrics": {k: (None if v is None else r(v)) for k, v in d["metrics"].items()},
        "gates": [
            {"gate": g["gate"], "name": g["name"], "status": g["status"], "summary": g["summary"]}
            for g in d["gates"]
        ],
        "value_of_information": None
        if d["value_of_information"] is None
        else {
            k: (r(v) if isinstance(v, float) else v)
            for k, v in d["value_of_information"].items()
            if k
            in (
                "evpi",
                "value_vs_candidate",
                "investigation_cost",
                "worth_investigating",
                "labels",
                "probabilities",
                "input",
            )
        },
    }


# ------------------------------------------------------------------ cases from benchmark samples

TARGETS = [
    ("investigate", "inventory_record_error"),
    ("reject", "stale_supplier_snapshot"),
    ("defer", "stale_sales_history"),
    ("escalate", "supplier_failure"),
    ("escalate", "lead_time_increase"),
    ("recommend", "budget_reduction"),
    ("recommend", "demand_collapse"),
    ("recommend", ""),
    ("escalate", ""),
    ("reject", ""),
]

TITLES = {
    "inventory_record_error": "Shelf ran empty yesterday but the record shows stock carried over",
    "stale_supplier_snapshot": "The plan was built on supplier terms that have since changed",
    "stale_sales_history": "Sales data is two days late",
    "supplier_failure": "Primary supplier has stopped delivering",
    "lead_time_increase": "Primary supplier lead time has doubled",
    "budget_reduction": "Procurement budget was cut in half",
    "demand_collapse": "Demand has dropped sharply",
    "transport_disruption": "Expedited freight is unavailable",
    "combined": "Supplier failure, demand spike and budget cut at once",
    "forecast_shift": "Demand is running above the forecast",
    "": "Routine replenishment",
}


OUTCOME_EVENT = {
    "reject": "stale_supplier_snapshot",
    "investigate": "inventory_record_error",
    "defer": "stale_sales_history",
}


def _title(events: str, outcome: str = "") -> str:
    evs = [e for e in events.split("|") if e] if events else []
    pref = OUTCOME_EVENT.get(outcome)
    first = pref if pref in evs else (evs[0] if evs else "")
    return TITLES.get(first, first.replace("_", " ").capitalize())


def build_cases(cfg: dict[str, Any], vp: ValidatorParams, n_cases: int, k: int) -> list[dict[str, Any]]:
    run = latest_run(cfg)
    samples = read_json(run / "samples.json")
    panel = load_panel(cfg)
    store = ForecastStore(load_forecasts(cfg, "B"), list(cfg["forecast"]["quantiles"]))
    sid_index = {s: i for i, s in enumerate(panel.series_ids)}
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    for outcome, ev in TARGETS:
        pool = [
            x
            for x in samples
            if x["report_outcome"] == outcome and x["candidate"]["entity"]["entity_id"] not in used
        ]
        if ev:
            pool = [x for x in pool if ev in x.get("events", "").split("|")]
        else:
            pool = [x for x in pool if x["condition"] == "normal"] or pool
        if not pool:
            continue
        pool.sort(
            key=lambda x: (
                -x["candidate"]["entity"]["typical_daily_volume"]
                * x["context"]["financial_assumptions"]["price"],
                x["candidate"]["decision_id"],
            )
        )
        pick = pool[min(len(pool) - 1, 1)]
        chosen.append(pick)
        used.add(pick["candidate"]["entity"]["entity_id"])
        if len(chosen) >= n_cases:
            break
    cases = []
    for idx, s in enumerate(chosen):
        cand = DecisionCandidate.model_validate(s["candidate"])
        ctx = AuthoritativeContext.model_validate(s["context"])
        sid = cand.entity.entity_id
        day = cand.decision_day
        stale = cand.data_snapshot.history_days_missing
        fc = store.get("lgbm_quantile_recovered", sid_index[sid], day, 3, stale)
        q3 = np.maximum(fc.q, 0.0)
        S3 = sample_paths(
            q3,
            fc.levels,
            k,
            float(cfg["benchmark"]["scenario_day_correlation"]),
            stream("web-case", sid, day),
        )
        h = len(cand.forecast.quantiles) if cand.forecast else 2
        econ = econ_from(ctx.financial_assumptions)
        auth = supply_from(ctx.constraints, ctx.approval_threshold, ctx.max_share.get("expedite", 1.0))
        case_id = f"case-{idx + 1:02d}"
        mu = cand.entity.typical_daily_volume
        date = panel.dates[day - 1]
        recorded = np.array(cand.data_snapshot.state["on_hand_by_age"])
        verified = np.array(s["true_on_hand_by_age"])
        pipeline = np.array(cand.data_snapshot.state["pipeline_by_day"])
        case: dict[str, Any] = {
            "id": case_id,
            "title": _title(s.get("events", ""), s["report_outcome"]),
            "entity": {
                "series_id": sid,
                "store": sid.split("_")[0].lstrip("s"),
                "product": sid.split("_p")[-1],
                "category": cand.entity.category,
            },
            "day": int(day),
            "date": date,
            "condition": s["condition"],
            "events": [e for e in s.get("events", "").split("|") if e],
            "mu": r(mu),
            "revenue_scale": r(mu * econ.price),
            "economics": {
                "price": econ.price,
                "unit_cost": econ.unit_cost,
                "shelf_life": econ.shelf_life,
                "holding": econ.holding,
                "disposal": econ.disposal,
                "goodwill": econ.goodwill,
                "terminal_waste_risk": econ.terminal_waste_risk,
                "currency": "USD (assumed)",
            },
            "state": {
                "recorded_on_hand_by_age": [r(x) for x in recorded],
                "verified_on_hand_by_age": [r(x) for x in verified],
                "pipeline_by_day": [r(x) for x in pipeline],
            },
            "plan_terms": {
                "resources": [x.model_dump() for x in cand.constraints.resources],
                "budget": r(cand.constraints.budget),
            },
            "current_terms": {
                "resources": [x.model_dump() for x in ctx.constraints.resources],
                "budget": r(ctx.constraints.budget),
            },
            "approval_threshold": r(ctx.approval_threshold),
            "max_expedite_share": ctx.max_share.get("expedite", 1.0),
            "freshness_max_age_hours": ctx.freshness_max_age_hours,
            "data_age_hours": cand.data_snapshot.age_hours,
            "history_days_missing": stale,
            "signals": {k2: r(v) for k2, v in ctx.signals.items()},
            "investigation_cost": r(ctx.investigation_cost),
            "review_cost": r(ctx.review_cost),
            "forecast": {
                "levels": fc.levels,
                "quantiles": [[r(x, 3) for x in row] for row in q3],
                "model": "lgbm_quantile_recovered",
                "staleness_days": stale,
            },
            "scenarios": [[r(x, 3) for x in row] for row in S3],
            "candidate": {
                "orders": [r(x) for x in cand.action_vector()],
                "policy": "P3 (expected-cost MILP)",
                "claimed_expected_cost": None
                if cand.scenario_results is None
                else r(cand.scenario_results.expected_cost or 0),
            },
        }
        S3r = np.array(case["scenarios"])
        # Recompute the validation report on the shipped scenarios so the browser can reproduce it exactly.
        payload = cand.model_dump()
        if cand.forecast is not None:
            payload["forecast"]["quantiles"] = case["forecast"]["quantiles"][:h]
        payload["data_snapshot"]["state"] = {
            "on_hand_by_age": case["state"]["recorded_on_hand_by_age"],
            "pipeline_by_day": case["state"]["pipeline_by_day"],
        }
        cand_h = DecisionCandidate.model_validate(payload)
        ctx_r = context_for(case, auth, econ, case["signals"])
        rep = validate(cand_h, ctx_r, ADAPTER, vp, scenarios=S3r[:, : min(h, 3)] if cand.forecast else None)
        case["validation"] = report_dict(rep)
        h_case = int(min(3, horizon_for(auth.leads, auth.capacities)))
        alts = alternatives(
            np.array(case["candidate"]["orders"]),
            np.array(case["state"]["recorded_on_hand_by_age"]),
            pipeline,
            auth,
            econ,
            S3r[:, :h_case],
            case["review_cost"],
            vp.cvar_alpha,
            tolerance_margin=case["revenue_scale"],
        )
        case["horizon_days"] = h_case
        case["alternatives"] = [
            {
                **a,
                **{k2: r(v) for k2, v in a.items() if isinstance(v, float)},
                "orders": [r(x) for x in a["orders"]],
            }
            for a in alts
        ]
        best = studio_evaluate(case, {}, vp)
        no_action = next(a for a in case["alternatives"] if a["key"] == "no_action")
        case["priority"] = {
            "cost_of_inaction": r(no_action["expected_cost"] - best["best_expected"]["expected"]),
            "days_of_cover": r(float(recorded.sum()) / max(mu, 1e-9), 2),
            "downside": r(best["recommended"]["cvar"] - best["recommended"]["expected"]),
            "investigation_cost": case["investigation_cost"],
            "feasible": True,
        }
        case["fan"] = fan_chart(q3, fc.levels)
        cases.append(case)
    return cases


def fan_chart(q: np.ndarray, levels: list[float]) -> list[dict[str, float]]:
    lv = np.asarray(levels)
    out = []
    for t, row in enumerate(q):
        out.append(
            {
                "day": t,
                **{
                    f"p{int(round(p * 100))}": r(float(quantile_function(row, lv, np.array([p]))[0]), 3)
                    for p in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
                },
            }
        )
    return out


# ------------------------------------------------------------------ golden fixtures


def golden(cases: list[dict[str, Any]], vp: ValidatorParams) -> dict[str, Any]:
    rng = np.random.default_rng(7)
    evals = []
    for _ in range(6):
        L = int(rng.integers(2, 6))
        econ = UnitEconomics(
            float(rng.uniform(2, 9)),
            float(rng.uniform(1, 5)),
            L,
            0.05,
            0.1,
            0.6,
            float(rng.uniform(0.1, 0.5)),
        )
        cohorts = rng.uniform(0, 15, L).round(3)
        H = int(rng.integers(2, 4))
        pipe = rng.uniform(0, 8, H).round(3)
        leads = np.array([1, 1 + int(rng.integers(0, 2)), 0])
        costs_ = rng.uniform(1, 6, 3).round(3)
        orders = rng.uniform(0, 25, (5, 3)).round(3)
        demand = rng.gamma(4, 4, (20, H)).round(3)
        res = evaluate_actions(cohorts, pipe, orders, leads, costs_, demand, econ)
        evals.append(
            {
                "econ": econ.to_dict(),
                "cohorts": cohorts.tolist(),
                "pipeline": pipe.tolist(),
                "orders": orders.tolist(),
                "leads": leads.tolist(),
                "unit_costs": costs_.tolist(),
                "demand": demand.tolist(),
                "cost": res.cost.tolist(),
                "cvar90": cvar(res.cost, 0.9).tolist(),
            }
        )
    grids = []
    for c in cases[:3]:
        sup = _supply(c, {})
        h = horizon_for(sup.leads, sup.capacities)
        grids.append({"case": c["id"], "horizon": int(h), "grid": action_grid(sup, h, *GRID_SHAPE).tolist()})
    mods_list = [
        {},
        {"demand_shift": 0.3, "risk_weight": 0.7},
        {"primary_delay_days": 1, "budget_mult": 0.6},
        {"cost_change": 0.25, "alternate_eligible": False, "risk_weight": 0.0},
        {"use_verified": True, "expedite_available": False, "demand_shift": -0.2},
    ]
    studio = []
    for c in cases[:4]:
        for m in mods_list:
            studio.append({"case": c["id"], "mods": m, "result": studio_evaluate(c, m, vp)})
    return {
        "generated_at": utc_now(),
        "evaluate": evals,
        "grids": grids,
        "studio": studio,
        "tolerance": {"relative": 1e-9, "absolute": 1e-7},
    }


# ------------------------------------------------------------------ export


def export_all(cfg: dict[str, Any]) -> dict[str, Any]:
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    run = latest_run(cfg)
    manifest = read_json(run / "manifest.json")
    soft = float(manifest["tuning"].get("validator_soft_scale", 1.0))
    k = int(cfg["web"]["case_scenarios"])
    vp = validator_params(cfg, soft, k)
    summary = read_json(repo_path("artifacts", "benchmark", "summary.json"))
    fmetrics = read_json(repo_path("artifacts", "forecast", "metrics.json"))
    dq = read_json(layout(cfg).dq_report)
    sec_path = repo_path("artifacts", "benchmark", "secondary_cloud.json")
    secondary = read_json(sec_path) if sec_path.exists() else None

    cases = build_cases(cfg, vp, int(cfg["web"]["n_cases"]), min(k, CASE_SCENARIOS_MAX))
    meta = {
        "app_version": "0.1.0",
        "data_source": summary["meta"]["data_source"],
        "data_label": "Synthetic fixture (FreshRetailNet-50K schema)"
        if summary["meta"]["data_source"] == "synthetic_fixture"
        else "FreshRetailNet-50K (Dingdong-Inc, CC BY 4.0)",
        "run_id": summary["meta"]["run_id"],
        "config_hash": config_hash(cfg),
        "git_sha": git_sha(),
        "generated_at": utc_now(),
        "protocol_version": summary["meta"]["protocol_version"],
        "test_window_days": summary["meta"]["window"],
        "validator_params": params_dict(vp),
        "grid_shape": list(GRID_SHAPE),
        "currency_note": "Amounts use assumed unit economics on normalized volumes. They are not real company figures.",
        "attribution": "FreshRetailNet-50K, Dingdong-Inc, CC BY 4.0, arXiv:2505.16319",
        "export_date": dt.date.today().isoformat(),
    }
    write_json(WEB_DATA / "meta.json", meta, compact=True)
    write_json(WEB_DATA / "cases.json", {"cases": cases}, compact=True)
    bench = {
        k2: summary[k2]
        for k2 in (
            "meta",
            "main",
            "paired",
            "detection",
            "risk_coverage",
            "ablations",
            "forecast_variants",
            "sensitivity",
            "demand_bounds",
            "audit",
            "hypotheses",
            "risk_coverage_tuned_scale",
        )
        if k2 in summary
    }
    write_json(WEB_DATA / "benchmark.json", bench, compact=True)
    fstage = fmetrics["stage_B"]
    write_json(
        WEB_DATA / "forecast.json",
        {
            "data_source": fmetrics["data_source"],
            "quantiles": fmetrics["quantiles"],
            "stage": {
                k2: fstage[k2]
                for k2 in ("fit_targets", "calibration_targets", "forecast_targets", "recovery", "n_fit_rows")
            },
            "models": {
                m: {k2: v for k2, v in d.items() if k2 != "by_profile_instock"}
                for m, d in fstage["models"].items()
            },
            "censoring_experiment": fmetrics["censoring_experiment"],
        },
        compact=True,
    )
    write_json(
        WEB_DATA / "data_quality.json",
        {
            k2: dq[k2]
            for k2 in (
                "data_source",
                "ingested_at",
                "rows_raw",
                "rows_clean",
                "rows_quarantined",
                "quarantine_reasons",
                "n_series",
                "n_days",
                "date_range",
                "stock_count_hours",
                "checks",
                "daily",
                "profiles",
            )
        }
        | {
            "provenance": {
                k2: v
                for k2, v in dq["source_info"].items()
                if k2
                in (
                    "data_source",
                    "description",
                    "generator",
                    "params",
                    "attribution",
                    "volume_scale_factor",
                    "subset_seed",
                )
            }
        },
        compact=True,
    )
    if secondary:
        write_json(WEB_DATA / "secondary.json", secondary, compact=True)
    write_json(FIXTURES / "golden.json", golden(cases, vp), compact=True)
    samples = read_json(run / "samples.json")
    pick = next((x for x in samples if x["report_outcome"] == "reject"), samples[0] if samples else None)
    if pick is not None:
        bundle = {
            "format": "edi-decision-bundle",
            "version": 1,
            "candidate": pick["candidate"],
            "context": pick["context"],
            "note": "Example exported from the benchmark. Simulated data.",
        }
        write_json(WEB_DATA / "example_bundle.json", bundle)
    write_schemas()
    sizes = {p.name: p.stat().st_size for p in sorted(WEB_DATA.glob("*.json"))}
    return {"cases": len(cases), "bytes": sizes, "fixtures": str(FIXTURES / "golden.json")}


def write_schemas() -> list[Path]:
    from edi.integrations.mock_erp import PurchaseRequisition
    from edi.validation.schema import ValidationReport

    out = []
    for name, model in (
        ("decision_candidate.v1.json", DecisionCandidate),
        ("authoritative_context.v1.json", AuthoritativeContext),
        ("validation_report.v1.json", ValidationReport),
        ("mock_erp_requisition.v1.json", PurchaseRequisition),
    ):
        p = repo_path("schemas", name)
        write_json(p, model.model_json_schema())
        out.append(p)
    return out
