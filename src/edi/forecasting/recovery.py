"""Latent demand recovery from hourly stock flags.

Method (transparent and CPU-cheap): estimate each series' share of daily demand by hour from fully
in-stock days inside the fit window, shrunk toward its category profile. On a day with out-of-stock
hours, the observed sales cover only the in-stock share of demand, so

    recovered = observed / (1 - share_out)              when the in-stock share is at least 30%
    recovered = observed + share_out x trailing level   otherwise (low-confidence fallback)

with the ratio capped at `max_multiplier`. Demand lost within the hour a shelf runs empty is not
recovered (the flag is hourly), so the estimate is mildly conservative.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from edi.pipeline import Panel

LOW_CONFIDENCE_SHARE = 0.3


def in_stock_mask(panel: Panel) -> np.ndarray:
    return (panel.stockout_hours == 0) & ~panel.is_missing & np.isfinite(panel.sales)


def hourly_profiles(
    hours_sale: np.ndarray,
    usable: np.ndarray,
    category: np.ndarray,
    shrinkage: float,
) -> np.ndarray:
    """Return (S, 24) hourly demand shares from usable (in-stock, in-window) days."""
    h = np.where(usable[:, :, None], np.nan_to_num(hours_sale, nan=0.0), 0.0)
    series_tot = h.sum(axis=1)  # (S, 24)
    n_days = usable.sum(axis=1).astype(float)
    profiles = np.zeros_like(series_tot)
    for cat in np.unique(category):
        members = category == cat
        cat_tot = series_tot[members].sum(axis=0)
        cat_prof = cat_tot / cat_tot.sum() if cat_tot.sum() > 0 else np.full(24, 1 / 24)
        s_sum = series_tot[members].sum(axis=1, keepdims=True)
        s_prof = np.divide(
            series_tot[members], s_sum, out=np.tile(cat_prof, (members.sum(), 1)), where=s_sum > 0
        )
        w = n_days[members][:, None]
        profiles[members] = (w * s_prof + shrinkage * cat_prof) / (w + shrinkage)
    return profiles / profiles.sum(axis=1, keepdims=True)


def recover(
    sales: np.ndarray,
    status: np.ndarray,
    profiles: np.ndarray,
    max_multiplier: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Recover daily demand. Returns (recovered, share_out, low_confidence)."""
    share_out = np.clip((status * profiles[:, None, :]).sum(axis=2), 0.0, 1.0)
    in_share = 1.0 - share_out
    ratio = sales / np.maximum(in_share, 1.0 / max_multiplier)
    low = in_share < LOW_CONFIDENCE_SHARE
    recovered = np.where(np.isfinite(sales), ratio, np.nan)
    n_s, n_d = sales.shape
    for d in range(n_d):
        rows = low[:, d] & np.isfinite(sales[:, d])
        if not rows.any():
            continue
        lo = max(0, d - 7)
        window = recovered[rows, lo:d]
        with np.errstate(all="ignore"):
            level = np.nanmean(window, axis=1) if d > 0 else np.full(rows.sum(), np.nan)
        level = np.where(np.isfinite(level), level, sales[rows, d] / max(LOW_CONFIDENCE_SHARE, 1e-9))
        recovered[rows, d] = np.minimum(sales[rows, d] + share_out[rows, d] * level, level * max_multiplier)
    return recovered, share_out, low


def recovered_target(panel: Panel, fit_end: int, cfg: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    rc = cfg["recovery"]
    usable = in_stock_mask(panel)
    usable[:, fit_end:] = False
    prof = hourly_profiles(panel.hours_sale, usable, panel.category, rc["profile_shrinkage"])
    rec, share_out, low = recover(panel.sales, panel.status, prof, rc["max_multiplier"])
    rec = np.where(panel.stockout_hours > 0, rec, panel.sales)  # unchanged on in-stock days
    info = {
        "fit_end": fit_end,
        "stockout_days": int((panel.stockout_hours > 0).sum()),
        "low_confidence_days": int((low & (panel.stockout_hours > 0)).sum()),
        "mean_uplift_on_stockout_days": float(
            np.nanmean((rec - panel.sales)[panel.stockout_hours > 0])
            if (panel.stockout_hours > 0).any()
            else 0.0
        ),
    }
    return rec, info


def censoring_experiment(panel: Panel, fit_end: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Controlled recovery test on artificially censored in-stock days (truth is known)."""
    rc = cfg["recovery"]
    rng = np.random.default_rng(rc["censor_seed"])
    usable = in_stock_mask(panel) & (panel.sales > 0)
    usable[:, :28] = False
    usable[:, fit_end:] = False
    cand = np.argwhere(usable)
    n_pick = int(len(cand) * rc["censor_fraction"])
    picked = cand[rng.choice(len(cand), size=n_pick, replace=False)]
    cutoffs = rng.integers(12, 21, size=n_pick)

    status = panel.status.copy()
    hours = np.nan_to_num(panel.hours_sale.copy(), nan=0.0)
    for (i, d), c in zip(picked, cutoffs):
        status[i, d, c:] = 1.0
        hours[i, d, c:] = 0.0
    censored_sales = panel.sales.copy()
    censored_sales[picked[:, 0], picked[:, 1]] = hours[picked[:, 0], picked[:, 1]].sum(axis=1)

    profile_mask = usable.copy()
    profile_mask[picked[:, 0], picked[:, 1]] = False
    prof = hourly_profiles(panel.hours_sale, profile_mask, panel.category, rc["profile_shrinkage"])
    rec, _, low = recover(censored_sales, status, prof, rc["max_multiplier"])

    truth = panel.sales[picked[:, 0], picked[:, 1]]
    naive = censored_sales[picked[:, 0], picked[:, 1]]
    recd = rec[picked[:, 0], picked[:, 1]]

    def summary(est: np.ndarray, mask: np.ndarray) -> dict[str, float]:
        t, e = truth[mask], est[mask]
        return {
            "n": int(mask.sum()),
            "mae": float(np.mean(np.abs(e - t))),
            "bias_pct": float(100 * (e.sum() - t.sum()) / t.sum()),
            "wape_pct": float(100 * np.abs(e - t).sum() / t.sum()),
        }

    all_mask = np.ones(len(truth), dtype=bool)
    buckets = {
        "cutoff_12_14": cutoffs <= 14,
        "cutoff_15_17": (cutoffs >= 15) & (cutoffs <= 17),
        "cutoff_18_20": cutoffs >= 18,
    }
    out: dict[str, Any] = {
        "design": "in-stock days censored from a random hour in [12, 20]; truth is the observed full-day sales",
        "fit_end": fit_end,
        "observed_as_demand": summary(naive, all_mask),
        "profile_recovery": summary(recd, all_mask),
        "low_confidence_share": float(low[picked[:, 0], picked[:, 1]].mean()),
        "by_cutoff": {
            k: {"observed_as_demand": summary(naive, m), "profile_recovery": summary(recd, m)}
            for k, m in buckets.items()
            if m.any()
        },
    }
    if panel.latent is not None:
        so = (panel.stockout_hours > 0) & ~panel.is_missing
        so[:, fit_end:] = False
        rec_real, _ = recovered_target(panel, fit_end, cfg)
        t = panel.latent[so]
        out["synthetic_genuine_stockouts"] = {
            "n": int(so.sum()),
            "observed_bias_pct": float(100 * (np.nansum(panel.sales[so]) - t.sum()) / t.sum()),
            "recovered_bias_pct": float(100 * (np.nansum(rec_real[so]) - t.sum()) / t.sum()),
            "observed_mae": float(np.nanmean(np.abs(panel.sales[so] - t))),
            "recovered_mae": float(np.nanmean(np.abs(rec_real[so] - t))),
            "note": "synthetic ground truth; not available for real data",
        }
    return out
