"""Forecast accuracy and calibration metrics."""

from __future__ import annotations

import numpy as np


def pinball(y: np.ndarray, q: np.ndarray, levels: list[float]) -> float:
    """Mean pinball loss over rows and quantile levels. q has shape (n, len(levels))."""
    diff = y[:, None] - q
    tau = np.asarray(levels)[None, :]
    return float(np.mean(np.maximum(tau * diff, (tau - 1) * diff)))


def wape(y: np.ndarray, yhat: np.ndarray) -> float | None:
    denom = float(np.sum(np.abs(y)))
    return None if denom == 0 else float(np.sum(np.abs(y - yhat)) / denom)


def bias(y: np.ndarray, yhat: np.ndarray) -> float | None:
    denom = float(np.sum(y))
    return None if denom == 0 else float(np.sum(yhat - y) / denom)


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    return float(np.mean((y >= lo) & (y <= hi)))


def evaluate(y: np.ndarray, q: np.ndarray, point: np.ndarray, levels: list[float]) -> dict[str, float | None]:
    ok = np.isfinite(y)
    y, q, point = y[ok], q[ok], point[ok]
    if len(y) == 0:
        return {"n": 0}
    lv = list(levels)
    i05, i10, i90, i95 = lv.index(0.05), lv.index(0.1), lv.index(0.9), lv.index(0.95)
    out: dict[str, float | None] = {
        "n": float(len(y)),
        "mae": float(np.mean(np.abs(y - point))),
        "wape": wape(y, point),
        "bias": bias(y, point),
        "pinball": pinball(y, q, lv),
        "coverage80": coverage(y, q[:, i10], q[:, i90]),
        "coverage90": coverage(y, q[:, i05], q[:, i95]),
        "width80_rel": float(np.mean(q[:, i90] - q[:, i10]) / max(np.mean(y), 1e-9)),
    }
    for j, tau in enumerate(lv):
        out[f"calib_{tau}"] = float(np.mean(y <= q[:, j]))
    return out
