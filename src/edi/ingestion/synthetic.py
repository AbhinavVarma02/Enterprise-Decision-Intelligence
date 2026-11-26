"""Deterministic synthetic fixture with the exact FreshRetailNet-50K columns.

Everything here is simulated. The fixture exists so engineering and tests can run when the real
dataset cannot be downloaded (ADR-0002). Unlike real data it also writes the true latent demand,
which makes censored-demand recovery and leakage logic checkable against ground truth.

Generative story per store-product series:
  latent daily mean = base x weekday x trend x holiday x promotion x weather x AR(1) shock
  hourly latent demand = gamma-Poisson around (daily mean x category hour profile)
  opening shelf stock is drawn around expected demand by an imperfect store ordering process
  hourly sales = demand served until the shelf is empty; empty hours are flagged out of stock
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from edi.core import sha256_file, utc_now, write_json, write_parquet
from edi.ingestion.schema import FRN_COLUMNS, HOURS, STOCK_COUNT_HOURS

START_DATE = dt.date(2024, 3, 28)
N_DAYS = 97  # 90 train + 7 eval, matching the official split lengths
HOLIDAYS = {
    dt.date(2024, 4, 4),
    dt.date(2024, 4, 5),
    dt.date(2024, 4, 6),
    dt.date(2024, 5, 1),
    dt.date(2024, 5, 2),
    dt.date(2024, 5, 3),
    dt.date(2024, 5, 4),
    dt.date(2024, 5, 5),
    dt.date(2024, 6, 10),
}
# Injected raw-data defects that the quality layer must catch (documented, deterministic).
N_DUPLICATES = 4
N_NULL_DISCOUNT = 2
N_NEGATIVE_SALE = 1
N_BAD_HOURS_LENGTH = 1


@dataclass(frozen=True)
class SyntheticFixture:
    raw: pd.DataFrame
    latent: pd.DataFrame
    params: dict[str, object]


def _hour_profile(category: int, rng: np.random.Generator) -> np.ndarray:
    hours = np.arange(HOURS, dtype=float)
    morning = np.exp(-0.5 * ((hours - (9.0 + 0.5 * category)) / 1.6) ** 2)
    evening = np.exp(-0.5 * ((hours - 18.5) / 1.8) ** 2)
    weight_evening = 1.2 + 0.25 * category + rng.normal(0, 0.05)
    prof = morning + weight_evening * evening + 0.15
    prof[(hours < 6) | (hours > 21)] = 0.0
    return prof / prof.sum()


def generate(n_series: int = 80, n_stores: int = 8, seed: int = 20261125) -> SyntheticFixture:
    if n_series < 4 or n_stores < 1:
        raise ValueError("need at least 4 series and 1 store")
    rng = np.random.default_rng(seed)
    dates = [START_DATE + dt.timedelta(days=i) for i in range(N_DAYS)]
    dow = np.array([d.weekday() for d in dates])
    t = np.arange(N_DAYS) / (N_DAYS - 1)

    store_city = rng.integers(1, 4, size=n_stores)
    store_mgmt = rng.integers(1, 3, size=n_stores)
    series_store = np.arange(n_series) % n_stores + 1
    series_cat = rng.choice(4, size=n_series, p=[0.3, 0.3, 0.2, 0.2]) + 1
    # Products repeat across stores, as in real assortment data; (store, product) stays unique.
    n_products = max(4, n_series // 2)
    series_product = np.empty(n_series, dtype=np.int64)
    used: set[tuple[int, int]] = set()
    for i in range(n_series):
        while True:
            p = int(rng.integers(0, n_products))
            if (int(series_store[i]), p) not in used:
                used.add((int(series_store[i]), p))
                series_product[i] = 10_000 + p
                break

    base = np.clip(rng.lognormal(np.log(14.0), 0.65, n_series), 2.5, 90.0)
    weekday_amp = rng.uniform(0.08, 0.28, n_series)
    dow_mult = 1.0 + weekday_amp[:, None] * np.where(dow >= 5, 1.0, np.where(dow == 4, 0.4, -0.15))[None, :]
    trend = 1.0 + rng.normal(0, 0.06, n_series)[:, None] * (t[None, :] - 0.5) * 2

    holiday = np.array([d in HOLIDAYS for d in dates], dtype=np.int32)
    holiday_lift = 1.0 + np.where(series_cat == 4, 0.35, 0.18)[:, None] * holiday[None, :]

    promo = rng.random((n_series, N_DAYS)) < 0.08
    discount = np.where(promo, rng.choice([0.7, 0.8, 0.9], size=(n_series, N_DAYS)), 1.0)
    activity = (promo & (rng.random((n_series, N_DAYS)) < 0.85)).astype(np.int32)
    promo_lift = discount ** (-1.8)

    city_temp_offset = rng.normal(0, 2.0, 4)
    temp = 14.0 + 12.0 * t[None, :] + city_temp_offset[store_city[series_store - 1]][:, None]
    temp = temp + rng.normal(0, 2.0, (n_series, N_DAYS))
    wet = rng.random((n_series, N_DAYS)) < 0.35
    precip = np.where(wet, rng.gamma(0.8, 6.0, (n_series, N_DAYS)), 0.0)
    humidity = np.clip(55 + 1.2 * precip + rng.normal(0, 8, (n_series, N_DAYS)), 20, 100)
    wind = np.clip(rng.gamma(2.0, 1.0, (n_series, N_DAYS)), 0, 9)
    weather_lift = np.exp(-0.012 * np.minimum(precip, 30.0))
    weather_lift = weather_lift * np.where(series_cat[:, None] == 2, 1.0 + 0.012 * (temp - 20.0), 1.0)

    shock = np.zeros((n_series, N_DAYS))
    eps = rng.normal(0, 0.16, (n_series, N_DAYS))
    for d in range(N_DAYS):
        shock[:, d] = (0.45 * shock[:, d - 1] if d else 0.0) + eps[:, d]
    daily_mean = base[:, None] * dow_mult * trend * holiday_lift * promo_lift * weather_lift * np.exp(shock)

    profiles = np.stack([_hour_profile(int(c), rng) for c in series_cat])  # (S, 24)
    hourly_mean = daily_mean[:, :, None] * profiles[:, None, :]  # (S, D, 24)
    dispersion = 8.0
    gamma = rng.gamma(dispersion, 1.0 / dispersion, hourly_mean.shape)
    latent_hours = rng.poisson(hourly_mean * gamma).astype(float)

    # Imperfect store ordering: opening stock around expected demand with series-level bias.
    series_bias = rng.lognormal(np.log(1.22), 0.12, n_series)
    day_noise = rng.lognormal(0.0, 0.2, (n_series, N_DAYS))
    opening = np.round(daily_mean * series_bias[:, None] * day_noise)

    remaining = opening.copy()
    hours_sale = np.zeros_like(latent_hours)
    status = np.zeros(latent_hours.shape, dtype=np.int32)
    for h in range(HOURS):
        empty = remaining <= 0
        status[:, :, h] = empty.astype(np.int32)
        sold = np.minimum(latent_hours[:, :, h], np.maximum(remaining, 0))
        hours_sale[:, :, h] = sold
        remaining = remaining - sold
    # Closed hours carry no demand; report them as in stock when the shelf still has product.
    stock_cnt = status[:, :, list(STOCK_COUNT_HOURS)].sum(axis=2).astype(np.int32)

    rows = []
    latent_rows = []
    for i in range(n_series):
        store = int(series_store[i])
        for d in range(N_DAYS):
            rows.append(
                {
                    "city_id": int(store_city[store - 1]),
                    "store_id": store,
                    "management_group_id": int(store_mgmt[store - 1]),
                    "first_category_id": int(series_cat[i]),
                    "second_category_id": int(series_cat[i] * 10 + (series_product[i] % 3)),
                    "third_category_id": int(series_cat[i] * 100 + (series_product[i] % 7)),
                    "product_id": int(series_product[i]),
                    "dt": dates[d].isoformat(),
                    "sale_amount": float(hours_sale[i, d].sum()),
                    "hours_sale": hours_sale[i, d].tolist(),
                    "stock_hour6_22_cnt": int(stock_cnt[i, d]),
                    "hours_stock_status": status[i, d].tolist(),
                    "discount": float(discount[i, d]),
                    "holiday_flag": int(holiday[d]),
                    "activity_flag": int(activity[i, d]),
                    "precpt": round(float(precip[i, d]), 3),
                    "avg_temperature": round(float(temp[i, d]), 2),
                    "avg_humidity": round(float(humidity[i, d]), 2),
                    "avg_wind_level": round(float(wind[i, d]), 2),
                }
            )
            latent_rows.append(
                {
                    "store_id": store,
                    "product_id": int(series_product[i]),
                    "dt": dates[d].isoformat(),
                    "latent_daily": float(latent_hours[i, d].sum()),
                    "latent_mean": float(daily_mean[i, d]),
                    "opening_stock": float(opening[i, d]),
                }
            )
    raw = pd.DataFrame(rows)
    raw = _inject_defects(raw, rng)
    latent = pd.DataFrame(latent_rows)
    params = {
        "n_series": n_series,
        "n_stores": n_stores,
        "seed": seed,
        "n_days": N_DAYS,
        "start_date": START_DATE.isoformat(),
        "injected_defects": {
            "duplicates": N_DUPLICATES,
            "null_discount": N_NULL_DISCOUNT,
            "negative_sale": N_NEGATIVE_SALE,
            "bad_hours_length": N_BAD_HOURS_LENGTH,
        },
    }
    return SyntheticFixture(raw=raw, latent=latent, params=params)


def _inject_defects(raw: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    raw = raw.copy()
    n = len(raw)
    picks = rng.choice(n, size=N_NULL_DISCOUNT + N_NEGATIVE_SALE + N_BAD_HOURS_LENGTH, replace=False)
    null_idx = picks[:N_NULL_DISCOUNT]
    neg_idx = picks[N_NULL_DISCOUNT : N_NULL_DISCOUNT + N_NEGATIVE_SALE]
    bad_idx = picks[N_NULL_DISCOUNT + N_NEGATIVE_SALE :]
    raw.loc[null_idx, "discount"] = np.nan
    raw.loc[neg_idx, "sale_amount"] = -1.0
    for i in bad_idx:
        # pandas-stubs cannot type list-valued object cells.
        raw.at[i, "hours_sale"] = list(raw.at[i, "hours_sale"])[:23]  # type: ignore[assignment,arg-type]
    dup = raw.iloc[rng.choice(n, size=N_DUPLICATES, replace=False)]
    return pd.concat([raw, dup], ignore_index=True)


def write_fixture(out_dir: Path, n_series: int, n_stores: int, seed: int) -> dict[str, object]:
    """Generate and write train/eval parquet files, latent truth and a provenance record."""
    fx = generate(n_series=n_series, n_stores=n_stores, seed=seed)
    split_date = (START_DATE + dt.timedelta(days=90)).isoformat()
    train = fx.raw[fx.raw["dt"] < split_date]
    eval_ = fx.raw[fx.raw["dt"] >= split_date]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": out_dir / "train.parquet",
        "eval": out_dir / "eval.parquet",
        "latent": out_dir / "latent_demand.parquet",
    }
    write_parquet(train, paths["train"])
    write_parquet(eval_, paths["eval"])
    write_parquet(fx.latent, paths["latent"])
    provenance: dict[str, object] = {
        "data_source": "synthetic_fixture",
        "description": "Deterministic synthetic fixture with FreshRetailNet-50K columns. Not real data.",
        "generated_at": utc_now(),
        "generator": "edi.ingestion.synthetic.generate",
        "params": fx.params,
        "columns": list(FRN_COLUMNS),
        "files": {k: {"path": p.name, "sha256": sha256_file(p)} for k, p in paths.items()},
    }
    write_json(out_dir / "PROVENANCE.json", provenance)
    return provenance
