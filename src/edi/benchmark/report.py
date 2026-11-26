"""Benchmark report: metrics with cluster-bootstrap intervals, detection and risk-coverage analysis,
external-recommendation audit, hypothesis verdicts. Writes artifacts/benchmark/summary.json.

Hypothesis verdicts follow rules fixed here before results were read (see protocol section 1):
the rule text is stored next to each verdict.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from edi.benchmark.runner import violations
from edi.benchmark.stats import bootstrap_mean, excludes_zero
from edi.core import artifact_path, config_hash, git_sha, read_json, require_same_run, utc_now, write_json
from edi.forecasting.run import load_forecasts
from edi.optimization.milp import action_grid
from edi.pipeline import load_panel
from edi.simulation.engine import cvar, evaluate_actions, horizon_for
from edi.simulation.scenarios import sample_paths, stream
from edi.validation.engine import ValidatorParams, validate
from edi.validation.inventory import InventoryAdapter, econ_from, supply_from
from edi.validation.schema import AuthoritativeContext, DecisionCandidate

POLICY_ORDER = ["P1", "P2", "P3", "P4", "P5a", "P5b", "ORACLE"]
CONDITIONS = ["normal", "unreliable", "disruption"]


def latest_run(cfg: dict[str, Any]) -> Path:
    exact = artifact_path(cfg, "runs", f"{cfg['run_name']}-{config_hash(cfg)}")
    if (exact / "manifest.json").exists():
        return exact
    runs = sorted(
        artifact_path(cfg, "runs").glob(f"{cfg['run_name']}-*/manifest.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not runs:
        raise FileNotFoundError("no benchmark run found; run `edi benchmark` first")
    return runs[-1].parent


def _series_values(df: pd.DataFrame, col: str) -> pd.Series:
    """Per-series mean over realizations (the bootstrap cluster)."""
    return df.groupby("series_id")[col].mean()


def policy_metrics(tot: pd.DataFrame, dec: pd.DataFrame, B: int, seed: int) -> dict[str, Any]:
    t = tot.copy()
    t["cost_per_day"] = t["total"] / t["n_days"]
    per_series = _series_values(t, "cost_per_day")
    out: dict[str, Any] = {
        "cost_per_series_day": bootstrap_mean(per_series.to_numpy(), B, seed),
        "cvar90_series_cost_per_day": float(cvar(t["cost_per_day"].to_numpy(), 0.9)),
        "expected_procurement_per_day": float((t["procurement"] / t["n_days"]).mean()),
        "fill_rate": float(t["sales_units"].sum() / max(t["demand_units"].sum(), 1e-9)),
        "waste_rate": float(t["waste_units"].sum() / max(t["received_units"].sum(), 1e-9)),
        "working_capital_avg": float(t["inventory_value_days"].sum() / max(t["days"].sum(), 1)),
        "governance_cost_per_day": float((t["governance"] / t["n_days"]).mean()),
        "profit_per_day": float((t["profit"] / t["n_days"]).mean()),
        "n_series": int(t["series_id"].nunique()),
        "n_episodes": int(len(t)),
    }
    if len(dec):
        out["n_decision_days"] = int(len(dec))
        out["stockout_day_frequency"] = float((dec["lost"] > 1e-9).mean())
        out["hard_violations"] = int(dec["n_violations"].sum())
        out["hard_breach_decisions"] = int((dec["n_violations"] > 0).sum())
        out["hard_violation_rate"] = out["hard_breach_decisions"] / len(dec)
        out["candidate_solver_nonoptimal"] = int((~dec["status"].isin(["optimal", "rule"])).sum())
        if "exec_unsafe" in dec and dec["exec_unsafe"].notna().any():
            unsafe = dec["exec_unsafe"].astype(bool)
            out["unsafe_executed_decisions"] = int(unsafe.sum())
            out["unsafe_executed_rate"] = out["unsafe_executed_decisions"] / len(dec)
            if "exec_has_order" in dec:
                submitted = dec["exec_has_order"].astype(bool)
                out["n_positive_submissions"] = int(submitted.sum())
                out["n_unsafe_positive_submissions"] = int((unsafe & submitted).sum())
                out["n_unsafe_no_order"] = int((unsafe & ~submitted).sum())
        out["decision_ms_mean"] = float(dec["decision_ms"].mean())
        out["outcomes"] = dec["outcome"].value_counts().to_dict()
        out["approval_reviews"] = int(
            dec.get("approval_review", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()
        )
    return out


def paired(tot: pd.DataFrame, a: str, b: str, B: int, seed: int) -> dict[str, Any]:
    """Paired per-series difference a - b in cost per day (same series, realizations, worlds)."""
    t = tot.copy()
    t["cost_per_day"] = t["total"] / t["n_days"]
    pa = t[t["policy"] == a].set_index(["series_id", "realization"])["cost_per_day"]
    pb = t[t["policy"] == b].set_index(["series_id", "realization"])["cost_per_day"]
    if pa.empty or pb.empty:
        return {}
    j = pd.concat([pa.rename("a"), pb.rename("b")], axis=1)
    if j.isna().any().any() or j.index.has_duplicates:
        raise ValueError(f"comparison {a} vs {b} requires exactly one row per matched series and realization")
    j["d"] = j["a"] - j["b"]
    per_series = j.groupby(level=0)[["d", "b"]].mean()
    ci = bootstrap_mean(per_series["d"].to_numpy(), B, seed)
    base = float(per_series["b"].mean())
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(per_series), size=(B, len(per_series)))
    delta, baseline = per_series[["d", "b"]].to_numpy().T
    denom = baseline[indices].sum(axis=1)
    ratios = delta[indices].sum(axis=1)[denom != 0] / denom[denom != 0]
    out: dict[str, Any] = {
        "a": a,
        "b": b,
        "diff_cost_per_day": ci,
        "relative_diff": ci["mean"] / base if base else None,
        "relative_lo": float(np.quantile(ratios, 0.025)) if len(ratios) else None,
        "relative_hi": float(np.quantile(ratios, 0.975)) if len(ratios) else None,
        "excludes_zero": excludes_zero(ci),
        "b_mean": base,
    }
    ids = per_series.index.to_series().str.extract(r"^s(?P<store>\d+)_p(?P<product>\d+)$")
    if ids.notna().all().all():
        out["crossed_store_product"] = crossed_interval(delta, baseline, ids, B, seed)
    return out


def crossed_interval(
    delta: np.ndarray, baseline: np.ndarray, ids: pd.DataFrame, resamples: int, seed: int
) -> dict[str, float | int | None]:
    """Pigeonhole sensitivity analysis on paired series averages, conditional on this week."""
    rng = np.random.default_rng(seed)
    weights = np.ones((resamples, len(ids)), dtype=int)
    n_clusters = {}
    for col in ("store", "product"):
        groups, index = np.unique(ids[col].to_numpy(), return_inverse=True)
        n = len(groups)
        n_clusters[f"n_{col}"] = n
        weights *= rng.multinomial(n, np.full(n, 1 / n), size=resamples)[:, index]
    counts = weights.sum(axis=1)
    numer = weights @ delta
    denom = weights @ baseline
    means = numer[counts > 0] / counts[counts > 0]
    ratios = numer[denom != 0] / denom[denom != 0]
    return {
        **n_clusters,
        "resamples": int(len(means)),
        "lo": float(np.quantile(means, 0.025)),
        "hi": float(np.quantile(means, 0.975)),
        "relative_lo": float(np.quantile(ratios, 0.025)) if len(ratios) else None,
        "relative_hi": float(np.quantile(ratios, 0.975)) if len(ratios) else None,
    }


def detection(dec: pd.DataFrame) -> dict[str, Any]:
    d = dec.copy()
    unsafe = d["cand_unsafe"].astype(bool)
    flagged = d["outcome"] != "recommend"
    n_u, n_s = int(unsafe.sum()), int((~unsafe).sum())
    rec = d["outcome"] == "recommend"
    return {
        "n_candidates": int(len(d)),
        "n_unsafe": n_u,
        "n_unsafe_intercepted": int((flagged & unsafe).sum()),
        "n_safe_interventions": int((flagged & ~unsafe).sum()),
        "recall": float((flagged & unsafe).sum() / n_u) if n_u else None,
        "unnecessary_intervention_rate": float((flagged & ~unsafe).sum() / n_s) if n_s else None,
        "coverage": float(rec.mean()),
        "unsafe_rate_among_recommended": float((rec & unsafe).sum() / max(rec.sum(), 1)),
        "unsafe_rate_without_validation": float(unsafe.mean()),
        "outcomes": d["outcome"].value_counts().to_dict(),
        "outcomes_unsafe": d.loc[unsafe, "outcome"].value_counts().to_dict(),
        "by_event": {
            ev: {
                "n": int(len(g)),
                "unsafe": int(g["cand_unsafe"].sum()),
                "flagged_unsafe": int(((g["outcome"] != "recommend") & g["cand_unsafe"]).sum()),
                "flagged_safe": int(((g["outcome"] != "recommend") & ~g["cand_unsafe"].astype(bool)).sum()),
            }
            for ev, g in d.assign(ev=d["events"].replace("", "none")).groupby("ev")
        },
    }


def risk_coverage(dec: pd.DataFrame, cfg: dict[str, Any], base_scale: float = 1.0) -> list[dict[str, Any]]:
    """Recompute outcomes from stored gate metrics with soft thresholds scaled by s (hard rules fixed).
    Gate metrics were stored at the tuned scale `base_scale`; scales here are relative to the config."""
    v = cfg["validation"]
    d = dec.copy()
    unsafe = d["cand_unsafe"].astype(bool).to_numpy()
    rev = d["revenue_scale"].astype(float).to_numpy()
    tol4 = float(v["loss_tolerance_mult"]) * 0.25 * rev
    tol5 = float(v["stress_tolerance_mult"]) * 0.25 * rev
    hard = (
        (d["G2_status"] == "fail")
        | (d["G3_status"] == "fail")
        | (d["G1_status"] == "fail")
        | (d["G6_status"] == "fail")
    )
    approval = d["approval_required"].astype(bool)
    tail = d["tail_gain"].astype(float).fillna(0).to_numpy()
    stress = d["stress_gain"].astype(float).fillna(0).to_numpy()
    voi = d["value_vs_candidate"].astype(float).fillna(0).to_numpy()
    anomaly = d["anomaly"].astype(bool).to_numpy()
    inv_cost = d["investigation_cost"].astype(float).to_numpy()
    out = []
    for s in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, float("inf")):
        soft = (anomaly & (voi > s * inv_cost)) | (tail > s * tol4) | (stress > s * tol5)
        for incl_approval in (True, False):
            flagged = hard.to_numpy() | soft | (approval.to_numpy() & incl_approval)
            rec = ~flagged
            out.append(
                {
                    "threshold_scale": "hard rules only" if s == float("inf") else s,
                    "include_approval_routing": incl_approval,
                    "coverage": float(rec.mean()),
                    "unsafe_rate_among_recommended": float((rec & unsafe).sum() / max(rec.sum(), 1)),
                    "unsafe_caught": float((flagged & unsafe).sum() / max(unsafe.sum(), 1)),
                }
            )
    return out


# ------------------------------------------------------------------ external recommendation audit

FAULTS = [
    "unchanged",
    "quantity_x3",
    "no_order",
    "ineligible_supplier",
    "misreported_cost",
    "missing_forecast",
    "stale_snapshot",
    "phantom_record",
]


def _label(
    cand: DecisionCandidate,
    ctx: AuthoritativeContext,
    true_coh: np.ndarray,
    fq: np.ndarray,
    levels: list[float],
    cfg: dict[str, Any],
    key: str,
) -> bool:
    econ = econ_from(ctx.financial_assumptions)
    auth = supply_from(ctx.constraints)
    orders = np.array(cand.action_vector())
    viol, deliver = violations(orders, auth)
    h = horizon_for(auth.leads, auth.capacities)
    q = fq[:h] if len(fq) >= h else np.vstack([fq, np.repeat(fq[-1:], h - len(fq), axis=0)])
    S = sample_paths(q, levels, int(cfg["benchmark"]["scenarios"]), 0.5, stream("audit-label", key))
    pipe = np.zeros(h)
    p = cand.data_snapshot.state["pipeline_by_day"]
    pipe[: min(h, len(p))] = p[:h]
    grid = action_grid(auth, h)
    best = np.min(
        evaluate_actions(true_coh, pipe, grid, auth.leads, auth.unit_costs, S, econ).cost.mean(axis=1)
    )
    e = evaluate_actions(true_coh, pipe, deliver[None, :], auth.leads, auth.unit_costs, S, econ).cost.mean()
    thr = (
        float(cfg["benchmark"]["unsafe_regret_days_revenue"]) * cand.entity.typical_daily_volume * econ.price
    )
    return bool(viol) or (e - best) > thr


def audit(samples: list[dict[str, Any]], cfg: dict[str, Any], limit: int = 240) -> dict[str, Any]:
    params = ValidatorParams.from_config(cfg)
    adapter = InventoryAdapter()
    rows = []
    for i, s in enumerate(samples[:limit]):
        base = DecisionCandidate.model_validate(s["candidate"])
        ctx0 = AuthoritativeContext.model_validate(s["context"])
        true_coh = np.array(s["true_on_hand_by_age"])
        assert base.forecast is not None
        fq = np.array(base.forecast.quantiles)
        levels = base.forecast.levels
        mu = base.entity.typical_daily_volume
        for fault in FAULTS:
            c = base.model_copy(deep=True)
            ctx = ctx0.model_copy(deep=True)
            truth = true_coh.copy()
            if fault == "quantity_x3":
                c.action = {k: v * 3 for k, v in c.action.items()}
                c.scenario_results = None
            elif fault == "no_order":
                c.action = {k: 0.0 for k in c.action}
                c.scenario_results = None
            elif fault == "ineligible_supplier":
                total = sum(c.action.values())
                c.action = {"primary": 0.0, "alternate": max(total, mu * 0.5), "expedite": 0.0}
                for r in ctx.constraints.resources:
                    if r.name == "alternate":
                        r.eligible = False
                c.scenario_results = None
            elif fault == "misreported_cost":
                if c.scenario_results and c.scenario_results.expected_cost is not None:
                    c.scenario_results.expected_cost *= 0.6
            elif fault == "missing_forecast":
                c.forecast = None
            elif fault == "stale_snapshot":
                c.data_snapshot.age_hours = 80.0
                c.data_snapshot.history_days_missing = 3
            elif fault == "phantom_record":
                # an upstream planner believed a record with stock that does not exist and planned on it
                st = copy.deepcopy(c.data_snapshot.state)
                st["on_hand_by_age"][1 if len(st["on_hand_by_age"]) > 1 else 0] += 1.2 * mu
                c.data_snapshot.state = st
                ctx.signals = dict(ctx.signals, stockout_hours_yesterday=8.0)
                S_p = adapter.scenarios(c, params.n_scenarios, params.rho, stream("audit-plan", i))
                g = adapter.grid(c, ctx)
                cost_g = adapter.evaluate(c, ctx, g, S_p, terms="candidate").mean(axis=1)
                j = int(np.argmin(cost_g))
                c.action = {n: float(g[j, k]) for k, n in enumerate(("primary", "alternate", "expedite"))}
                c.scenario_results = (
                    c.scenario_results.model_copy(update={"expected_cost": float(cost_g[j])})
                    if c.scenario_results
                    else None
                )
            unsafe = _label(c, ctx, truth, fq, levels, cfg, f"{i}:{fault}")
            rep = validate(DecisionCandidate.model_validate(c.model_dump()), ctx, adapter, params)
            rows.append(
                {"fault": fault, "unsafe": unsafe, "outcome": rep.outcome, "condition": s.get("condition")}
            )
    df = pd.DataFrame(rows)
    by: dict[str, Any] = {}
    for fault_name, fault_rows in df.groupby("fault"):
        flagged = fault_rows["outcome"] != "recommend"
        unsafe_rows = fault_rows["unsafe"]
        by[str(fault_name)] = {
            "n": int(len(fault_rows)),
            "unsafe_share": float(unsafe_rows.mean()),
            "flagged_share": float(flagged.mean()),
            "recall_on_unsafe": float((flagged & unsafe_rows).sum() / max(unsafe_rows.sum(), 1)),
            "outcomes": fault_rows["outcome"].value_counts().to_dict(),
        }
    safe = df[~df["unsafe"].astype(bool)]
    u = df[df["unsafe"].astype(bool)]
    return {
        "n_base_candidates": int(min(limit, len(samples))),
        "n_evaluations": int(len(df)),
        "by_fault": by,
        "overall_recall_on_unsafe": float((u["outcome"] != "recommend").mean()) if len(u) else None,
        "false_alarm_rate_on_safe": float((safe["outcome"] != "recommend").mean()) if len(safe) else None,
        "note": "Faults are injected into real benchmark candidates; truth uses the simulator state at that decision.",
    }


# ------------------------------------------------------------------ hypotheses


def _kendall(a: list[float], b: list[float]) -> float:
    return float(kendalltau(a, b).statistic)


def _agreement_by_series(cfg: dict[str, Any], totals: pd.DataFrame, a: str, b: str) -> dict[str, Any]:
    panel = load_panel(cfg)
    forecasts = load_forecasts(cfg, "B")
    forecasts = forecasts.loc[
        forecasts["model"].isin([a, b]) & (forecasts["target_day"] >= cfg["windows"]["test_start"])
    ].copy()
    levels = np.array(cfg["forecast"]["quantiles"])
    si = forecasts["series"].to_numpy(dtype=int)
    day = forecasts["target_day"].to_numpy(dtype=int) - 1
    error = panel.sales[si, day, None] - forecasts[[f"q{x}" for x in levels]].to_numpy()
    forecasts["pinball"] = np.maximum(error * levels, error * (levels - 1)).mean(axis=1)
    forecasts["series_id"] = np.asarray(panel.series_ids)[si]
    loss = forecasts.groupby(["series_id", "model"])["pinball"].mean().unstack()
    cost = totals.groupby(["series_id", "policy"])["cost_per_day"].mean().unstack()
    differences = pd.concat([loss[a] - loss[b], cost[f"P3[{a}]"] - cost[f"P3[{b}]"]], axis=1).dropna()
    return {"n_series": len(differences), "kendall_tau": _kendall(*differences.to_numpy().T.tolist())}


def harness_invariants(dec: pd.DataFrame) -> dict[str, int]:
    """Checks on the simulation harness itself, not on the policies. Raises when one fails.

    When the validator rejects, or a stock count or review leads to a re-plan, the harness re-plans
    on the terms of record, so the executed order must respect them. A hard breach there would
    mean the harness, not the policy, produced it (this caught the bug fixed in amendment 2).
    """
    note = dec["reviewer_note"].fillna("")
    replanned = (dec["outcome"] == "reject") | (dec["reviewed"].astype(bool) & (note == ""))
    counted = (dec["outcome"] == "investigate") & ~dec["reviewed"].astype(bool) & (dec["governance_cost"] > 0)
    rows = dec[replanned | counted]
    bad = rows[rows["exec_hard_violation"].fillna(False).astype(bool)]
    if len(bad):
        sample = (
            bad[["series_id", "day", "policy", "condition", "experiment", "outcome"]]
            .head(5)
            .to_dict("records")
        )
        raise RuntimeError(
            f"harness invariant failed: {len(bad)} re-planned orders breach hard constraints, e.g. {sample}"
        )
    return {"replanned_orders_checked": int(len(rows)), "hard_breaches_after_replan": 0}


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    run = latest_run(cfg)
    manifest = read_json(run / "manifest.json")
    if manifest["config_hash"] != config_hash(cfg):
        raise ValueError("benchmark manifest config does not match the requested configuration")
    tot = pd.read_parquet(run / "series_totals.parquet")
    dec = pd.read_parquet(run / "decisions.parquet")
    invariants = harness_invariants(dec)
    samples = read_json(run / "samples.json")
    B = int(cfg["benchmark"]["bootstrap_resamples"])
    seed = 20261125
    fmetrics = read_json(artifact_path(cfg, "forecast", "metrics.json"))
    require_same_run(fmetrics, cfg, "artifacts/forecast/metrics.json")
    if fmetrics["data_source"] != manifest["data_source"]:
        raise ValueError("forecast and benchmark data sources differ")

    summary: dict[str, Any] = {
        "meta": {
            "run_id": manifest["run_id"],
            "run_name": cfg["run_name"],
            "config_hash": manifest["config_hash"],
            "data_source": manifest["data_source"],
            "dataset_revision": manifest.get("dataset_revision"),
            "protocol_version": manifest["protocol_version"],
            "n_series": manifest["n_series"],
            "realizations": manifest["realizations"],
            "window": [cfg["windows"]["test_start"], cfg["windows"]["test_end"]],
            "tuning": manifest["tuning"],
            "generated_at": utc_now(),
            "git_sha": manifest.get("git_sha", git_sha()),
            "runtime_seconds": manifest["runtime_seconds"],
            "n_decisions": manifest["n_decisions"],
            "currency_note": "Assumed unit economics applied to (normalized) volumes; not real money.",
            "harness_invariants": invariants,
        }
    }
    main_t = tot[tot["experiment"] == "main"]
    main_d = dec[dec["experiment"] == "main"]
    summary["main"] = {}
    summary["paired"] = {}
    summary["detection"] = {}
    for cond in CONDITIONS:
        t = main_t[main_t["condition"] == cond]
        d = main_d[main_d["condition"] == cond]
        summary["main"][cond] = {
            p: policy_metrics(t[t["policy"] == p], d[d["policy"] == p], B, seed)
            for p in POLICY_ORDER
            if (t["policy"] == p).any()
        }
        pairs = [
            ("P5a", "P3"),
            ("P5b", "P4"),
            ("P4", "P3"),
            ("P3", "P2"),
            ("P3", "P1"),
            ("P2", "P1"),
            ("P1", "ORACLE"),
            ("P3", "ORACLE"),
            ("P1", "P3"),
            ("P2", "P3"),
            ("P5b", "P3"),
            ("ORACLE", "P3"),
        ]
        summary["paired"][cond] = {f"{a}_vs_{b}": paired(t, a, b, B, seed) for a, b in pairs}
        summary["detection"][cond] = {p: detection(d[d["policy"] == p]) for p in ("P5a", "P5b")}
    p5 = main_d[main_d["policy"] == "P5a"]
    summary["risk_coverage"] = risk_coverage(p5, cfg, manifest["tuning"].get("validator_soft_scale", 1.0))
    summary["risk_coverage_tuned_scale"] = manifest["tuning"].get("validator_soft_scale", 1.0)

    abl_t = pd.concat([tot[tot["experiment"] == "ablation"], main_t[main_t["policy"].isin(["P3", "P5a"])]])
    summary["ablations"] = {}
    for cond in CONDITIONS:
        t = abl_t[abl_t["condition"] == cond]
        res = {}
        for p in [
            "P5a_no_stockout_aware",
            "P5a_no_voi",
            "P5a_no_escalation",
            "P5a_no_risk_review",
            "P5a_untuned",
        ]:
            res[p] = paired(t, p, "P5a", B, seed)
        res["P3_obs_vs_P3"] = paired(t, "P3_obs", "P3", B, seed)
        res["no_validation_P3_vs_P5a"] = paired(t, "P3", "P5a", B, seed)
        summary["ablations"][cond] = res

    fv = tot[tot["experiment"] == "forecast_variants"].copy()
    fv["cost_per_day"] = fv["total"] / fv["n_days"]
    rows = []
    stage_b = fmetrics["stage_B"]["models"]
    for policy_name, variant_rows in fv.groupby("policy"):
        model = str(policy_name)[3:-1]
        m = stage_b[model]
        ci = bootstrap_mean(_series_values(variant_rows, "cost_per_day").to_numpy(), B, seed)
        rows.append(
            {
                "model": model,
                "decision_cost_per_day": ci,
                "pinball_vs_observed": m["vs_observed_all"]["pinball"],
                "wape_vs_observed": m["vs_observed_all"]["wape"],
                "bias_vs_observed": m["vs_observed_all"]["bias"],
                "pinball_vs_latent": m.get("vs_latent_all", {}).get("pinball"),
                "bias_vs_latent": m.get("vs_latent_all", {}).get("bias"),
                "coverage80_vs_latent": m.get("vs_latent_all", {}).get("coverage80"),
            }
        )
    rows.sort(key=lambda r: r["decision_cost_per_day"]["mean"])
    summary["forecast_variants"] = rows
    best_acc = min(rows, key=lambda r: r["pinball_vs_observed"])["model"]
    best_cost = rows[0]["model"]
    tau_obs = _kendall(
        [r["pinball_vs_observed"] for r in rows], [r["decision_cost_per_day"]["mean"] for r in rows]
    )
    lat = [r["pinball_vs_latent"] for r in rows]
    tau_lat = (
        _kendall(lat, [r["decision_cost_per_day"]["mean"] for r in rows])
        if all(x is not None for x in lat)
        else None
    )
    h1_pair = paired(fv, f"P3[{best_acc}]", f"P3[{best_cost}]", B, seed) if best_acc != best_cost else {}

    sens = []
    for exp in sorted(x for x in tot["experiment"].unique() if str(x).startswith("sensitivity:")):
        t = tot[tot["experiment"] == exp]
        pr = paired(t, "P5a", "P3", B, seed)
        sens.append({"setting": exp.split(":", 1)[1], "P5a_vs_P3": pr})
    summary["sensitivity"] = sens
    bounds = {}
    for exp in sorted(x for x in tot["experiment"].unique() if str(x).startswith("demand_bound:")):
        t = tot[tot["experiment"] == exp]
        t2 = t.assign(cost_per_day=t["total"] / t["n_days"])
        bounds[exp.split(":", 1)[1]] = {
            p: float(_series_values(t2[t2["policy"] == p], "cost_per_day").mean())
            for p in t2["policy"].unique()
        }
    summary["demand_bounds"] = {
        "note": "Reference demand on stockout days replaced by observed sales (lower) or recovery x 1.25 (upper).",
        "cost_per_day": bounds,
    }
    summary["audit"] = audit(samples, cfg)

    # hypothesis verdicts (rules fixed in code before inspecting results)
    hyp = []
    hyp.append(
        {
            "id": "H1",
            "statement": "Better forecast accuracy does not necessarily produce lower decision cost.",
            "rule": "supported if the most accurate model on observed sales is not the lowest-cost model and their paired "
            "cost difference CI excludes zero; partially supported if the models differ but the CI includes zero",
            "evidence": {
                "best_accuracy_model": best_acc,
                "best_cost_model": best_cost,
                "kendall_tau_observed": tau_obs,
                "kendall_tau_latent": tau_lat,
                "paired_cost_difference": h1_pair,
                "per_series_error_cost_agreement": _agreement_by_series(cfg, fv, best_acc, best_cost)
                if best_acc != best_cost
                else None,
            },
            "verdict": (
                "supported"
                if best_acc != best_cost and h1_pair.get("excludes_zero")
                else "partially supported"
                if best_acc != best_cost
                else "not supported"
            ),
        }
    )
    pu = summary["paired"]["unreliable"]["P5a_vs_P3"]
    m3 = summary["main"]["unreliable"]["P3"]
    m5 = summary["main"]["unreliable"]["P5a"]
    safer = m5.get("unsafe_executed_rate", 1) < m3.get("unsafe_executed_rate", 0)
    cheaper = bool(pu) and pu["diff_cost_per_day"]["hi"] < 0
    hyp.append(
        {
            "id": "H2",
            "statement": "Under unreliable data, validation lowers unsafe decisions and total cost including governance.",
            "rule": "supported if P5a executes fewer unsafe decisions than P3 and the paired cost CI is below zero; "
            "partially supported if only one holds",
            "evidence": {
                "unsafe_P3": m3.get("unsafe_executed_rate"),
                "unsafe_P5a": m5.get("unsafe_executed_rate"),
                "paired": pu,
            },
            "verdict": "supported"
            if safer and cheaper
            else ("partially supported" if safer or cheaper else "not supported"),
        }
    )
    pn = summary["paired"]["normal"]["P5a_vs_P3"]
    hyp.append(
        {
            "id": "H3",
            "statement": "Under normal operations the validation layer's net cost change is within +/-2%.",
            "rule": "supported if the relative paired difference CI lies within [-2%, +2%]; not supported otherwise",
            "evidence": {"paired": pn},
            "verdict": "supported"
            if pn and pn["relative_lo"] >= -0.02 and pn["relative_hi"] <= 0.02
            else "not supported",
        }
    )
    h4 = {}
    for cond in CONDITIONS:
        a, b = summary["main"][cond]["P4"], summary["main"][cond]["P3"]
        h4[cond] = {
            "cvar90_P4": a["cvar90_series_cost_per_day"],
            "cvar90_P3": b["cvar90_series_cost_per_day"],
            "mean_P4": a["cost_per_series_day"]["mean"],
            "mean_P3": b["cost_per_series_day"]["mean"],
        }
    ok4 = [
        h4[c]["cvar90_P4"] < h4[c]["cvar90_P3"] and h4[c]["mean_P4"] < 1.05 * h4[c]["mean_P3"]
        for c in CONDITIONS
    ]
    hyp.append(
        {
            "id": "H4",
            "statement": "Mean-CVaR optimization lowers CVaR90 at an expected-cost increase below 5%.",
            "rule": "supported if it holds in all three conditions; partially if in some",
            "evidence": h4,
            "verdict": "supported" if all(ok4) else ("partially supported" if any(ok4) else "not supported"),
        }
    )
    ce = fmetrics["censoring_experiment"]
    hyp.append(
        {
            "id": "H5",
            "statement": "Hourly-profile recovery reduces error and bias on artificially censored days.",
            "rule": "supported if both MAE and absolute bias are lower than treating observed sales as demand",
            "evidence": {
                "observed_as_demand": ce["observed_as_demand"],
                "profile_recovery": ce["profile_recovery"],
            },
            "verdict": "supported"
            if ce["profile_recovery"]["mae"] < ce["observed_as_demand"]["mae"]
            and abs(ce["profile_recovery"]["bias_pct"]) < abs(ce["observed_as_demand"]["bias_pct"])
            else "not supported",
        }
    )
    summary["hypotheses"] = hyp
    path = artifact_path(cfg, "benchmark", "summary.json")
    write_json(path, summary)
    summary["paths"] = {"summary": str(path), "run": str(run)}
    return summary
