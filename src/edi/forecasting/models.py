"""Forecast models. All models work on targets normalized by the series' trailing 28-day mean."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np

from edi.forecasting.features import FEATURES, Design


@dataclass
class Prediction:
    point: np.ndarray  # original units
    q: np.ndarray  # (n, L) original units, sorted and nonnegative


def _finalize(point_n: np.ndarray, q_n: np.ndarray, scale: np.ndarray) -> Prediction:
    q_n = np.sort(q_n, axis=1)  # rearrangement keeps quantiles coherent
    q = np.maximum(q_n, 0.0) * scale[:, None]
    point = np.maximum(point_n, 0.0) * scale
    return Prediction(point=point, q=q)


def _residual_offsets(y_n: np.ndarray, p_n: np.ndarray, levels: list[float]) -> np.ndarray:
    ok = np.isfinite(y_n) & np.isfinite(p_n)
    return np.quantile(y_n[ok] - p_n[ok], levels)


def conformal_deltas(y_n: np.ndarray, q_n: np.ndarray, levels: list[float]) -> np.ndarray:
    """One-sided split-conformal shift per quantile level (finite-sample corrected)."""
    ok = np.isfinite(y_n)
    y_n, q_n = y_n[ok], q_n[ok]
    n = len(y_n)
    if n == 0:
        return np.zeros(len(levels))
    deltas = np.empty(len(levels))
    for j, tau in enumerate(levels):
        scores = np.sort(y_n - q_n[:, j])
        k = min(n, max(1, math.ceil((n + 1) * tau)))
        deltas[j] = scores[k - 1]
    return deltas


def _lgb_params(params: dict[str, Any], **extra: Any) -> tuple[dict[str, Any], int]:
    """Translate sklearn-style names in the config to native LightGBM parameters."""
    rename = {
        "min_child_samples": "min_data_in_leaf",
        "subsample": "bagging_fraction",
        "subsample_freq": "bagging_freq",
        "colsample_bytree": "feature_fraction",
        "random_state": "seed",
        "n_jobs": "num_threads",
    }
    out = {rename.get(k, k): v for k, v in params.items() if k != "n_estimators"}
    out.update(extra)
    out.setdefault("deterministic", True)
    out.setdefault("force_row_wise", True)
    return out, int(params.get("n_estimators", 200))


def _train(X: Any, y: np.ndarray, params: dict[str, Any], **extra: Any) -> lgb.Booster:
    p, rounds = _lgb_params(params, **extra)
    ds = lgb.Dataset(X, label=y, categorical_feature=["category"] if "category" in X.columns else "auto")
    return lgb.train(p, ds, num_boost_round=rounds)


class BaseModel:
    name = "base"

    def __init__(self, levels: list[float]):
        self.levels = levels
        self.offsets = np.zeros(len(levels))
        self.deltas = np.zeros(len(levels))

    def point_n(self, d: Design) -> np.ndarray:
        raise NotImplementedError

    def quantiles_n(self, d: Design) -> np.ndarray:
        return self.point_n(d)[:, None] + self.offsets[None, :]

    def fit(self, d: Design) -> BaseModel:
        self.offsets = _residual_offsets(d.y_norm, self.point_n(d), self.levels)
        return self

    def calibrate(self, d: Design) -> BaseModel:
        self.deltas = conformal_deltas(d.y_norm, np.sort(self.quantiles_n(d), axis=1), self.levels)
        return self

    def predict(self, d: Design) -> Prediction:
        q_n = np.sort(self.quantiles_n(d), axis=1) + self.deltas[None, :]
        return _finalize(self.point_n(d), q_n, d.scale)


class SeasonalNaive(BaseModel):
    name = "seasonal_naive"

    def point_n(self, d: Design) -> np.ndarray:
        x = d.X["same_dow_1w"].to_numpy()
        return np.where(np.isfinite(x), x, np.nan_to_num(d.X["mean7"].to_numpy(), nan=1.0))


class MovingAverage(BaseModel):
    """Seven-day mean adjusted by the same-weekday ratio over the last four weeks."""

    name = "moving_average"

    def point_n(self, d: Design) -> np.ndarray:
        m7 = np.nan_to_num(d.X["mean7"].to_numpy(), nan=1.0)
        ratio = d.X["dow_ratio"].to_numpy()
        return m7 * np.where(np.isfinite(ratio) & (ratio > 0), ratio, 1.0)


@dataclass
class LGBMPoint(BaseModel):
    levels: list[float]
    params: dict[str, Any]
    features: list[str] = field(default_factory=lambda: list(FEATURES))
    name: str = "lgbm_point"

    def __post_init__(self) -> None:
        super().__init__(self.levels)
        self.model: lgb.Booster | None = None

    def fit(self, d: Design) -> LGBMPoint:
        ok = np.isfinite(d.y_norm)
        self.model = _train(d.X.loc[ok, self.features], d.y_norm[ok], self.params, objective="regression")
        self.offsets = _residual_offsets(d.y_norm, self.point_n(d), self.levels)
        return self

    def point_n(self, d: Design) -> np.ndarray:
        assert self.model is not None
        return np.asarray(self.model.predict(d.X[self.features]))


@dataclass
class LGBMQuantile(BaseModel):
    levels: list[float]
    params: dict[str, Any]
    features: list[str] = field(default_factory=lambda: list(FEATURES))
    name: str = "lgbm_quantile"

    def __post_init__(self) -> None:
        super().__init__(self.levels)
        self.models: list[lgb.Booster] = []

    def fit(self, d: Design) -> LGBMQuantile:
        ok = np.isfinite(d.y_norm)
        X, y = d.X.loc[ok, self.features], d.y_norm[ok]
        self.models = [_train(X, y, self.params, objective="quantile", alpha=tau) for tau in self.levels]
        return self

    def quantiles_n(self, d: Design) -> np.ndarray:
        return np.column_stack([m.predict(d.X[self.features]) for m in self.models])

    def point_n(self, d: Design) -> np.ndarray:
        return self.quantiles_n(d)[:, self.levels.index(0.5)]

    def predict(self, d: Design) -> Prediction:
        q_n = np.sort(np.sort(self.quantiles_n(d), axis=1) + self.deltas[None, :], axis=1)
        return _finalize(q_n[:, self.levels.index(0.5)], q_n, d.scale)
