"""Leakage-safe feature construction for direct multi-horizon forecasting.

A row is (series i, origin day o, horizon h) with target day t = o + h. Features use the target
history only through day o. Allowed target-day inputs are calendar and planned promotion fields
(holiday, discount, activity), per ADR-0005. Weather enters only as trailing means ending at o.
Days are 1-based; array column d-1 holds day d.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from edi.pipeline import Panel

FEATURES = [
    "h",
    "dow_target",
    "holiday_target",
    "discount_target",
    "activity_target",
    "lag1",
    "lag2",
    "lag3",
    "lag4",
    "lag5",
    "lag6",
    "lag7",
    "same_dow_1w",
    "same_dow_2w",
    "mean7",
    "std7",
    "dow_ratio",
    "stockout_hours_o",
    "stockout_share7",
    "temp_trail3",
    "precip_trail3",
    "category",
]
PROMO_FEATURES = ["discount_target", "activity_target"]
SCALE_FLOOR = 0.5


@dataclass
class Design:
    X: pd.DataFrame
    y_norm: np.ndarray  # NaN when the target is unknown or out of range
    y: np.ndarray
    scale: np.ndarray
    series: np.ndarray
    origin: np.ndarray
    h: np.ndarray
    target_day: np.ndarray


def _nanmean(a: np.ndarray, axis: int) -> np.ndarray:
    with np.errstate(all="ignore"):
        cnt = np.isfinite(a).sum(axis=axis)
        return np.where(cnt > 0, np.nansum(a, axis=axis) / np.maximum(cnt, 1), np.nan)


def _nanstd(a: np.ndarray, axis: int) -> np.ndarray:
    m = _nanmean(a, axis)
    dev = (a - np.expand_dims(m, axis)) ** 2
    return np.sqrt(_nanmean(dev, axis))


def build(panel: Panel, target: np.ndarray, origins: list[int], horizons: list[int], max_target: int) -> Design:
    """Build features for every series, origin in `origins` and h in `horizons` with t <= max_target."""
    dates = pd.to_datetime(pd.Series(panel.dates))
    dow = dates.dt.weekday.to_numpy()
    n_s = panel.n_series
    blocks = []
    for o in origins:
        if o < 28:
            raise ValueError("origins need 28 days of history")
        hist = target[:, o - 28 : o]  # days o-27..o
        mean28 = _nanmean(hist, 1)
        scale = np.maximum(np.nan_to_num(mean28, nan=SCALE_FLOOR), SCALE_FLOOR)
        last7 = target[:, o - 7 : o]
        mean7 = _nanmean(last7, 1)
        std7 = _nanstd(last7, 1)
        so7 = (panel.stockout_hours[:, o - 7 : o] > 0).mean(axis=1)
        temp3 = _nanmean(panel.temp[:, o - 3 : o], 1)
        prec3 = _nanmean(panel.precip[:, o - 3 : o], 1)
        lags = [target[:, o - 1 - k] for k in range(7)]  # day o, o-1, ..., o-6 (column = day - 1)
        for h in horizons:
            t = o + h
            if t > max_target:
                continue
            ti = t - 1
            same1 = target[:, ti - 7]
            same2 = target[:, ti - 14]
            dow_cols = [ti - 7 * k for k in range(1, 5)]
            dow_mean = _nanmean(target[:, dow_cols], 1)
            df = pd.DataFrame(
                {
                    "h": np.full(n_s, h, dtype=float),
                    "dow_target": np.full(n_s, dow[ti], dtype=float),
                    "holiday_target": panel.holiday[:, ti],
                    "discount_target": panel.discount[:, ti],
                    "activity_target": panel.activity[:, ti],
                    **{f"lag{k + 1}": lags[k] / scale for k in range(7)},
                    "same_dow_1w": same1 / scale,
                    "same_dow_2w": same2 / scale,
                    "mean7": mean7 / scale,
                    "std7": std7 / scale,
                    "dow_ratio": dow_mean / scale,
                    "stockout_hours_o": panel.stockout_hours[:, o - 1],
                    "stockout_share7": so7,
                    "temp_trail3": temp3,
                    "precip_trail3": prec3,
                    "category": panel.category.astype(float),
                }
            )
            y = target[:, ti] if ti < target.shape[1] else np.full(n_s, np.nan)
            blocks.append(
                (df, y, scale, np.arange(n_s), np.full(n_s, o), np.full(n_s, h), np.full(n_s, t))
            )
    if not blocks:
        raise ValueError("no rows: check origins, horizons and max_target")
    X = pd.concat([b[0] for b in blocks], ignore_index=True)[FEATURES]
    y = np.concatenate([b[1] for b in blocks])
    scale = np.concatenate([b[2] for b in blocks])
    return Design(
        X=X,
        y_norm=y / scale,
        y=y,
        scale=scale,
        series=np.concatenate([b[3] for b in blocks]),
        origin=np.concatenate([b[4] for b in blocks]),
        h=np.concatenate([b[5] for b in blocks]),
        target_day=np.concatenate([b[6] for b in blocks]),
    )
