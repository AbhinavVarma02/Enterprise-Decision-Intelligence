"""Cluster bootstrap over series (protocol section 6)."""

from __future__ import annotations

import numpy as np


def bootstrap_mean(values: np.ndarray, resamples: int, seed: int) -> dict[str, float]:
    """Percentile 95% interval for the mean of per-series values (one value per cluster)."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(resamples, len(v)))
    means = v[idx].mean(axis=1)
    return {
        "mean": float(v.mean()),
        "lo": float(np.quantile(means, 0.025)),
        "hi": float(np.quantile(means, 0.975)),
        "n": int(len(v)),
    }


def excludes_zero(ci: dict[str, float]) -> bool:
    return bool(ci["lo"] > 0 or ci["hi"] < 0)
