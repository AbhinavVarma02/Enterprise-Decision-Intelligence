"""Benchmark experiments (protocol sections 3 to 6): tuning, main comparison, ablations, forecast
variants (H1), sensitivity and demand-bound runs. Results are written as raw per-decision and
per-series tables plus decision samples for the audit experiment and the web application.
"""

from __future__ import annotations

import copy
import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from edi.benchmark.runner import ForecastStore, PolicySpec, SeriesSetup, make_setup, run_episode
from edi.core import config_hash, get_logger, git_sha, log_event, repo_path, utc_now, write_json, write_parquet
from edi.forecasting.run import load_forecasts
from edi.pipeline import Panel, layout, load_panel
from edi.simulation.scenarios import make_world
from edi.validation.engine import ValidatorParams

log = get_logger("edi.benchmark")

_G: dict[str, Any] = {}


@dataclass(frozen=True)
class Cell:
    experiment: str
    phase: str  # tuning | test
    condition: str
    realization: int
    spec: PolicySpec
    overrides: tuple[tuple[str, float], ...] = ()
    reference: str = "default"  # default | lower | upper
    econ_variant: str = ""  # "" | goodwill_x2 | holding_x2
    keep_samples: int = 0


def select_series(panel: Panel, n: int) -> np.ndarray:
    """Deterministic, evenly spaced subset in sorted series order."""
    if n >= panel.n_series:
        return np.arange(panel.n_series)
    return np.unique(np.linspace(0, panel.n_series - 1, n).round().astype(int))


def references(cfg: dict[str, Any], panel: Panel) -> dict[str, dict[str, np.ndarray]]:
    root = layout(cfg).root / "curated"
    out: dict[str, dict[str, np.ndarray]] = {}
    for stage in ("A", "B"):
        rec = np.load(root / f"recovered_{stage}.npy")
        default = panel.latent if panel.latent is not None else np.where(np.isfinite(rec), rec, 0.0)
        so = panel.stockout_hours > 0
        obs = np.nan_to_num(panel.sales, nan=0.0)
        out[stage] = {
            "default": np.nan_to_num(default, nan=0.0),
            "lower": np.where(so, obs, np.nan_to_num(default, nan=0.0)),
            "upper": np.where(so, np.nan_to_num(rec, nan=0.0) * 1.25, np.nan_to_num(default, nan=0.0)),
        }
    return out


def _econ_cfg(cfg: dict[str, Any], variant: str) -> dict[str, Any]:
    if not variant:
        return cfg
    c = copy.deepcopy(cfg)
    key, mult = {"goodwill_x2": ("goodwill", 2.0), "goodwill_x0.5": ("goodwill", 0.5), "holding_x2": ("holding", 2.0)}[variant]
    for p in c["economics"]["profiles"].values():
        p[key] = p[key] * mult
    return c


def _init(cfg: dict[str, Any]) -> None:
    panel = load_panel(cfg)
    levels = list(cfg["forecast"]["quantiles"])
    _G["cfg"] = cfg
    _G["panel"] = panel
    _G["stores"] = {s: ForecastStore(load_forecasts(cfg, s), levels) for s in ("A", "B")}
    _G["refs"] = references(cfg, panel)
    _G["vparams"] = ValidatorParams.from_config(cfg)


def _run_chunk(args: tuple[list[int], list[Cell]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    series_idx, cells = args
    cfg, panel = _G["cfg"], _G["panel"]
    w = cfg["windows"]
    totals_rows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for cell in cells:
        stage = "A" if cell.phase == "tuning" else "B"
        window = (w["tune_start"], w["tune_end"]) if cell.phase == "tuning" else (w["test_start"], w["test_end"])
        fit_end = w["a_fit_end"] if stage == "A" else w["b_fit_end"]
        ccfg = _econ_cfg(cfg, cell.econ_variant)
        ref = _G["refs"][stage][cell.reference]
        for i in series_idx:
            setup: SeriesSetup = make_setup(panel, int(i), ref, ccfg, fit_end)
            world = make_world(int(cfg["benchmark"]["seed"]), setup.series_id, cell.condition, cell.realization,
                               window, cell.phase, float(cfg["benchmark"]["fault_rate"]))
            t0 = time.perf_counter()
            res = run_episode(setup, world, cell.spec, _G["stores"][stage], ccfg, window, _G["vparams"],
                              dict(cell.overrides), keep_samples=cell.keep_samples)
            tags = {"experiment": cell.experiment, "phase": cell.phase, "condition": cell.condition,
                    "realization": cell.realization, "policy": cell.spec.pid, "reference": cell.reference,
                    "econ_variant": cell.econ_variant, "overrides": ",".join(f"{k}={v}" for k, v in cell.overrides),
                    "series_id": setup.series_id, "profile": setup.profile, "mu": setup.mu}
            t = res.totals.to_dict()
            totals_rows.append({**tags, **t, "events": "|".join(world.labels()),
                                "runtime_s": time.perf_counter() - t0, "n_days": window[1] - window[0] + 1,
                                "daily_revenue_scale": setup.mu * setup.econ.price})
            for d in res.decisions:
                d.update({k: tags[k] for k in ("experiment", "phase", "reference", "econ_variant", "overrides", "profile")})
                decisions.append(d)
            for s in res.samples:
                samples.append({**s, "experiment": cell.experiment, "condition": cell.condition, "policy": cell.spec.pid,
                                "events": "|".join(world.labels())})
    return totals_rows, decisions, samples


def run_cells(cfg: dict[str, Any], cells: list[Cell], series_idx: np.ndarray, n_jobs: int) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    chunks = [list(c) for c in np.array_split(series_idx, max(1, n_jobs * 2)) if len(c)]
    jobs = [(c, cells) for c in chunks]
    totals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    if n_jobs <= 1:
        _init(cfg)
        results = [_run_chunk(j) for j in jobs]
    else:
        ctx = mp.get_context("fork") if "fork" in mp.get_all_start_methods() else mp.get_context()
        with ProcessPoolExecutor(max_workers=n_jobs, mp_context=ctx, initializer=_init, initargs=(cfg,)) as ex:
            results = list(ex.map(_run_chunk, jobs))
    for t, d, s in results:
        totals += t
        decisions += d
        samples += s
    return pd.DataFrame(totals), pd.DataFrame(decisions), samples


def _per_day_cost(df: pd.DataFrame) -> pd.Series:
    return df["total"] / df["n_days"]


def tune(cfg: dict[str, Any], series_idx: np.ndarray, n_jobs: int) -> dict[str, Any]:
    """Tune the base-stock safety factor and the CVaR weight on the tuning window (days 77-90)."""
    bc = cfg["benchmark"]
    cells = []
    for cond in ("normal", "disruption"):
        for z in bc["base_stock_z_grid"]:
            cells.append(Cell("tuning", "tuning", cond, 0, PolicySpec(f"P1_z{z}", "base_stock", z=float(z))))
        for lam in bc["cvar_lambda_grid"]:
            cells.append(Cell("tuning", "tuning", cond, 0, PolicySpec(f"P4_l{lam}", "cvar", lam=float(lam))))
    totals, _, _ = run_cells(cfg, cells, series_idx, n_jobs)
    totals["cost_per_day"] = _per_day_cost(totals)
    agg = totals.groupby("policy")["cost_per_day"].mean()
    z_best = min(bc["base_stock_z_grid"], key=lambda z: agg[f"P1_z{z}"])
    lam_best = min(bc["cvar_lambda_grid"], key=lambda lam: agg[f"P4_l{lam}"])
    return {"z": float(z_best), "lambda": float(lam_best), "grid": agg.round(4).to_dict(),
            "objective": "mean total cost per series-day over normal and tuning-set disruptions, days 77-90"}


def main_specs(z: float, lam: float) -> list[PolicySpec]:
    return [
        PolicySpec("P1", "base_stock", z=z, label="Base-stock rule (tuned)"),
        PolicySpec("P2", "deterministic", label="Point forecast + deterministic MILP"),
        PolicySpec("P3", "saa", label="Calibrated quantiles + expected-cost MILP"),
        PolicySpec("P4", "cvar", lam=lam, label="Calibrated quantiles + mean-CVaR MILP"),
        PolicySpec("P5a", "validated", wrapped="saa", label="Validation framework over P3"),
        PolicySpec("P5b", "validated", wrapped="cvar", lam=lam, label="Validation framework over P4"),
        PolicySpec("ORACLE", "oracle", label="Retrospective oracle (not deployable)"),
    ]


def ablation_specs() -> list[PolicySpec]:
    return [
        PolicySpec("P3_obs", "saa", model="lgbm_quantile_observed", label="P3 without stockout-aware forecasts"),
        PolicySpec("P5a_no_stockout_aware", "validated", wrapped="saa", model="lgbm_quantile_observed",
                   label="P5a without stockout-aware forecasts"),
        PolicySpec("P5a_no_voi", "validated", wrapped="saa", use_voi=False, label="P5a without value of information"),
        PolicySpec("P5a_no_escalation", "validated", wrapped="saa", use_escalation=False, label="P5a without escalation"),
        PolicySpec("P5a_no_risk_review", "validated", wrapped="saa", risk_review=False,
                   label="P5a with expected-cost review"),
    ]


FORECAST_VARIANTS = [
    "seasonal_naive",
    "moving_average",
    "lgbm_point",
    "lgbm_quantile_observed",
    "lgbm_quantile_recovered",
    "lgbm_quantile_recovered_nopromo",
]


def run_all(cfg: dict[str, Any], n_jobs: int = 2) -> dict[str, Any]:
    t_start = time.perf_counter()
    panel = load_panel(cfg)
    bc = cfg["benchmark"]
    series_idx = select_series(panel, int(bc["n_series"]))
    run_id = f"{cfg['run_name']}-{config_hash(cfg)}"
    out_dir = repo_path("artifacts", "runs", run_id)
    log_event(log, "benchmark start", run_id=run_id, series=len(series_idx), data_source=panel.data_source)

    tuning = tune(cfg, series_idx, n_jobs)
    log_event(log, "tuning done", **{k: tuning[k] for k in ("z", "lambda")})
    z, lam = tuning["z"], tuning["lambda"]
    R = int(bc["realizations"])
    conditions = ("normal", "unreliable", "disruption")
    cells: list[Cell] = []
    for cond in conditions:
        for r in range(R):
            for spec in main_specs(z, lam):
                keep = 60 if spec.pid == "P5a" else 0
                cells.append(Cell("main", "test", cond, r, spec, keep_samples=keep))
            for spec in ablation_specs():
                cells.append(Cell("ablation", "test", cond, r, spec))
    for r in range(R):
        for m in FORECAST_VARIANTS:
            cells.append(Cell("forecast_variants", "test", "normal", r, PolicySpec(f"P3[{m}]", "saa", model=m)))
    if bc.get("sensitivity", True):
        sens: list[tuple[str, tuple[tuple[str, float], ...], str]] = [
            ("review_x0.5", (("review_mult", 0.5), ("investigation_mult", 0.5)), ""),
            ("review_x2", (("review_mult", 2.0), ("investigation_mult", 2.0)), ""),
            ("review_x4", (("review_mult", 4.0), ("investigation_mult", 4.0)), ""),
            ("reviewer_error_0", (("reviewer_error_rate", 0.0),), ""),
            ("reviewer_error_0.3", (("reviewer_error_rate", 0.3),), ""),
            ("goodwill_x2", (), "goodwill_x2"),
            ("goodwill_x0.5", (), "goodwill_x0.5"),
            ("holding_x2", (), "holding_x2"),
        ]
        for name, ov, ev in sens:
            for r in range(R):
                for spec in (PolicySpec("P3", "saa"), PolicySpec("P5a", "validated", wrapped="saa")):
                    cells.append(Cell(f"sensitivity:{name}", "test", "unreliable", r, spec, ov, econ_variant=ev))
        for ref in ("lower", "upper"):
            for r in range(R):
                for spec in main_specs(z, lam)[:5]:
                    cells.append(Cell(f"demand_bound:{ref}", "test", "normal", r, spec, reference=ref))

    totals, decisions, samples = run_cells(cfg, cells, series_idx, n_jobs)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(totals, out_dir / "series_totals.parquet")
    dec = decisions.copy()
    for col in ("orders_candidate", "orders_executed"):
        dec[col] = dec[col].map(lambda v: ",".join(f"{x:.4f}" for x in v))
    write_parquet(dec, out_dir / "decisions.parquet")
    write_json(out_dir / "samples.json", samples, compact=True)
    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "git_sha": git_sha(),
        "config_hash": config_hash(cfg),
        "config_path": cfg.get("_config_path"),
        "data_source": panel.data_source,
        "n_series": int(len(series_idx)),
        "series_ids": [panel.series_ids[i] for i in series_idx],
        "realizations": R,
        "tuning": tuning,
        "n_cells": len(cells),
        "n_decisions": int(len(decisions)),
        "runtime_seconds": round(time.perf_counter() - t_start, 1),
        "protocol_version": "1.0",
    }
    write_json(out_dir / "manifest.json", manifest)
    log_event(log, "benchmark done", run_id=run_id, decisions=len(decisions), seconds=manifest["runtime_seconds"])
    return manifest


def _replace_spec(spec: PolicySpec, **kw: Any) -> PolicySpec:
    return replace(spec, **kw)
