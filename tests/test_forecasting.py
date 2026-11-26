"""Leakage prevention, demand recovery, calibration and metric definitions."""

from __future__ import annotations

import copy

import numpy as np
import pytest

from edi.forecasting import features as F
from edi.forecasting.metrics import evaluate, pinball, wape
from edi.forecasting.models import LGBMQuantile, MovingAverage, conformal_deltas
from edi.forecasting.recovery import (
    censoring_experiment,
    hourly_profiles,
    in_stock_mask,
    recover,
    recovered_target,
)

ALLOWED_TARGET_DAY = {"holiday_target", "discount_target", "activity_target"}


def test_no_future_leakage(panel) -> None:
    """Perturbing anything after the origin (except planned target-day calendar fields) must not move features."""
    origin, horizons = 40, [1, 2, 3]
    y = panel.sales.copy()
    base = F.build(panel, y, [origin], horizons, 97).X
    p2 = copy.deepcopy(panel)
    y2 = y.copy()
    y2[:, origin:] = 999.0  # every day after the origin
    p2.stockout_hours[:, origin:] = 16
    p2.temp[:, origin:] = -50.0
    p2.precip[:, origin:] = 500.0
    p2.discount[:, origin + 4 :] = 0.1  # beyond the latest target day
    pert = F.build(p2, y2, [origin], horizons, 97).X
    np.testing.assert_allclose(base.to_numpy(), pert.to_numpy(), equal_nan=True)


def test_target_day_promotions_are_the_only_forward_inputs(panel) -> None:
    origin = 40
    p2 = copy.deepcopy(panel)
    p2.discount[:, origin] = 0.5  # day origin + 1 = first target day
    a = F.build(panel, panel.sales, [origin], [1], 97).X
    b = F.build(p2, p2.sales, [origin], [1], 97).X
    changed = {c for c in a.columns if not np.allclose(a[c], b[c], equal_nan=True)}
    assert changed <= ALLOWED_TARGET_DAY and changed


def test_quantiles_are_coherent_and_nonnegative(panel, base_cfg) -> None:
    levels = base_cfg["forecast"]["quantiles"]
    y = panel.sales
    fit = F.build(panel, y, list(range(28, 60)), [1, 2], 60)
    pred = F.build(panel, y, [70], [1, 2], 97)
    for model in (
        MovingAverage(levels),
        LGBMQuantile(levels, dict(base_cfg["forecast"]["lgbm"], n_estimators=20)),
    ):
        model.fit(fit)
        pr = model.predict(pred)
        assert (np.diff(pr.q, axis=1) >= -1e-12).all()
        assert (pr.q >= 0).all() and (pr.point >= 0).all()


def test_conformal_shift_reaches_nominal_level_on_calibration_set(rng) -> None:
    y = rng.normal(size=400)
    q = np.zeros((400, 3)) + np.array([-0.5, 0.0, 0.5])
    levels = [0.1, 0.5, 0.9]
    d = conformal_deltas(y, q, levels)
    cover = [(y <= q[:, j] + d[j]).mean() for j in range(3)]
    assert all(c >= lvl for c, lvl in zip(cover, levels))


def test_metric_definitions() -> None:
    assert wape(np.zeros(3), np.ones(3)) is None
    y = np.array([1.0, 2.0])
    q = np.array([[0.0], [3.0]])
    # tau=0.5: losses 0.5*1 and 0.5*1
    assert pinball(y, q, [0.5]) == pytest.approx(0.5)
    out = evaluate(
        np.array([1.0, 2.0, np.nan]),
        np.tile([0.5, 0.9, 1.0, 1.5, 2.0, 2.5, 3.0], (3, 1)),
        np.array([1.5, 1.5, 1.5]),
        [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95],
    )
    assert out["n"] == 2 and out["coverage80"] == 1.0


def test_hourly_profiles_sum_to_one_and_recovery_math() -> None:
    hours = np.zeros((1, 2, 24))
    hours[0, :, 8] = 6.0
    hours[0, :, 18] = 4.0
    usable = np.array([[True, True]])
    prof = hourly_profiles(hours, usable, np.array([1]), shrinkage=0.0)
    assert prof.sum() == pytest.approx(1.0)
    assert prof[0, 18] == pytest.approx(0.4)
    status = np.zeros((1, 1, 24))
    status[0, 0, 17:] = 1  # evening out of stock: 40% of demand unobserved
    rec, share_out, low = recover(np.array([[6.0]]), status, prof, max_multiplier=4.0)
    assert share_out[0, 0] == pytest.approx(0.4)
    assert rec[0, 0] == pytest.approx(10.0)
    assert not low[0, 0]


def test_recovered_target_matches_observed_on_in_stock_days(panel, base_cfg) -> None:
    rec, info = recovered_target(panel, 69, base_cfg)
    ins = in_stock_mask(panel)
    np.testing.assert_allclose(rec[ins], panel.sales[ins])
    so = (panel.stockout_hours > 0) & np.isfinite(panel.sales)
    assert (rec[so] >= panel.sales[so] - 1e-9).all()
    assert info["stockout_days"] > 0


def test_controlled_censoring_recovery_reduces_bias(panel, base_cfg) -> None:
    res = censoring_experiment(panel, 69, base_cfg)
    assert res["observed_as_demand"]["bias_pct"] < -20
    assert abs(res["profile_recovery"]["bias_pct"]) < abs(res["observed_as_demand"]["bias_pct"]) / 3
    assert res["profile_recovery"]["mae"] < res["observed_as_demand"]["mae"]
