"""Two-stage forecasting run (protocol section 2).

Stage A: fit on targets <= a_fit_end, calibrate on (a_fit_end, a_cal_end], forecast the tuning window.
Stage B: refit on targets <= b_fit_end with the same hyperparameters, calibrate on (b_fit_end, b_cal_end],
forecast the final test window. No test-window value influences any choice.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from edi.core import artifact_path, get_logger, log_event, write_json, write_parquet
from edi.forecasting import features as F
from edi.forecasting.metrics import evaluate
from edi.forecasting.models import BaseModel, LGBMPoint, LGBMQuantile, MovingAverage, SeasonalNaive
from edi.forecasting.recovery import censoring_experiment, recovered_target
from edi.pipeline import Panel, layout

log = get_logger("edi.forecasting")

MODEL_SPECS = [
    # name, target, class, kwargs
    ("seasonal_naive", "observed"),
    ("moving_average", "observed"),
    ("lgbm_point", "observed"),
    ("lgbm_quantile_observed", "observed"),
    ("lgbm_quantile_recovered", "recovered"),
    ("lgbm_quantile_recovered_nopromo", "recovered"),
]
PRIMARY_MODEL = "lgbm_quantile_recovered"


def _make(name: str, levels: list[float], params: dict[str, Any]) -> BaseModel:
    if name == "seasonal_naive":
        return SeasonalNaive(levels)
    if name == "moving_average":
        return MovingAverage(levels)
    if name == "lgbm_point":
        return LGBMPoint(levels, params)
    if name == "lgbm_quantile_observed":
        return LGBMQuantile(levels, params, name=name)
    if name == "lgbm_quantile_recovered":
        return LGBMQuantile(levels, params, name=name)
    if name == "lgbm_quantile_recovered_nopromo":
        feats = [f for f in F.FEATURES if f not in F.PROMO_FEATURES]
        return LGBMQuantile(levels, params, features=feats, name=name)
    raise ValueError(name)


def forecast_path(cfg: dict[str, Any], stage: str) -> Any:
    return layout(cfg).root / "curated" / f"forecasts_{stage}.parquet"


def run_stage(
    panel: Panel, cfg: dict[str, Any], stage: str
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, np.ndarray]]:
    w = cfg["windows"]
    levels = list(cfg["forecast"]["quantiles"])
    horizons = list(cfg["forecast"]["horizons"])
    params = dict(cfg["forecast"]["lgbm"])
    if stage == "A":
        fit_end, cal_end, ws, we = w["a_fit_end"], w["a_cal_end"], w["tune_start"], w["tune_end"]
    else:
        fit_end, cal_end, ws, we = w["b_fit_end"], w["b_cal_end"], w["test_start"], w["test_end"]
    warm = w["warmup_end"]
    rec, rec_info = recovered_target(panel, fit_end, cfg)
    targets = {"observed": panel.sales, "recovered": rec}

    designs: dict[str, dict[str, F.Design]] = {}
    for tname, y in targets.items():
        fit = F.build(panel, y, list(range(warm, fit_end)), horizons, fit_end)
        cal = F.build(panel, y, list(range(fit_end - max(horizons) + 1, cal_end)), horizons, cal_end)
        keep = cal.target_day > fit_end
        cal = _filter(cal, keep)
        pred = F.build(
            panel, y, list(range(ws - 3, we)), horizons, we
        )  # stale-history decisions use origin d-3
        designs[tname] = {"fit": fit, "cal": cal, "pred": pred}

    rows = []
    metrics: dict[str, Any] = {}
    pred_design = designs["observed"]["pred"]
    obs_truth = pred_design.y
    instock = panel.stockout_hours[pred_design.series, pred_design.target_day - 1] == 0
    latent_truth = (
        panel.latent[pred_design.series, pred_design.target_day - 1] if panel.latent is not None else None
    )
    profiles = np.array(panel.profile)[pred_design.series]
    for name, tname in MODEL_SPECS:
        t0 = time.perf_counter()
        model = _make(name, levels, params)
        d = designs[tname]
        model.fit(d["fit"]).calibrate(d["cal"])
        pr = model.predict(d["pred"])
        elapsed = time.perf_counter() - t0
        assert np.array_equal(d["pred"].series, pred_design.series)
        df = pd.DataFrame(
            {
                "model": name,
                "series": d["pred"].series,
                "origin": d["pred"].origin,
                "h": d["pred"].h,
                "target_day": d["pred"].target_day,
                "point": pr.point,
                **{f"q{tau}": pr.q[:, j] for j, tau in enumerate(levels)},
            }
        )
        rows.append(df)
        m: dict[str, Any] = {
            "target": tname,
            "fit_seconds": round(elapsed, 2),
            "vs_observed_all": evaluate(obs_truth, pr.q, pr.point, levels),
            "vs_observed_instock": evaluate(np.where(instock, obs_truth, np.nan), pr.q, pr.point, levels),
            "vs_observed_stockout_days": evaluate(
                np.where(~instock, obs_truth, np.nan), pr.q, pr.point, levels
            ),
        }
        if latent_truth is not None:
            m["vs_latent_all"] = evaluate(latent_truth, pr.q, pr.point, levels)
            m["vs_latent_stockout_days"] = evaluate(
                np.where(~instock, latent_truth, np.nan), pr.q, pr.point, levels
            )
        m["by_profile_instock"] = {
            p: evaluate(np.where(instock & (profiles == p), obs_truth, np.nan), pr.q, pr.point, levels)
            for p in sorted(set(profiles))
        }
        metrics[name] = m
        log_event(log, "model done", stage=stage, model=name, seconds=round(elapsed, 2))
    out = pd.concat(rows, ignore_index=True)
    info = {
        "stage": stage,
        "fit_targets": [warm + 1, fit_end],
        "calibration_targets": [fit_end + 1, cal_end],
        "forecast_targets": [ws, we],
        "recovery": rec_info,
        "n_fit_rows": int(np.isfinite(designs["observed"]["fit"].y_norm).sum()),
        "models": metrics,
    }
    return out, info, targets


def _filter(d: F.Design, keep: np.ndarray) -> F.Design:
    return F.Design(
        X=d.X.loc[keep].reset_index(drop=True),
        y_norm=d.y_norm[keep],
        y=d.y[keep],
        scale=d.scale[keep],
        series=d.series[keep],
        origin=d.origin[keep],
        h=d.h[keep],
        target_day=d.target_day[keep],
    )


def run(cfg: dict[str, Any], panel: Panel) -> dict[str, Any]:
    t0 = time.perf_counter()
    summary: dict[str, Any] = {
        "run_name": cfg["run_name"],
        "data_source": panel.data_source,
        "quantiles": cfg["forecast"]["quantiles"],
    }
    for stage in ("A", "B"):
        df, info, targets = run_stage(panel, cfg, stage)
        write_parquet(df, forecast_path(cfg, stage))
        np.save(layout(cfg).root / "curated" / f"recovered_{stage}.npy", targets["recovered"])
        summary[f"stage_{stage}"] = info
    summary["censoring_experiment"] = censoring_experiment(panel, cfg["windows"]["b_fit_end"], cfg)
    summary["runtime_seconds"] = round(time.perf_counter() - t0, 1)
    write_json(artifact_path(cfg, "forecast", "metrics.json"), summary)
    return summary


def load_forecasts(cfg: dict[str, Any], stage: str) -> pd.DataFrame:
    return pd.read_parquet(forecast_path(cfg, stage))
