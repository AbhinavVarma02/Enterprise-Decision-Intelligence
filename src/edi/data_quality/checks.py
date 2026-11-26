"""Data quality checks.

Hard row-level failures are quarantined with a reason code. Soft checks are reported, never silently
fixed, except the documented imputation of a missing `discount` as 1.0 (no discount), which is flagged
on the row.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from edi.ingestion.schema import FRN_COLUMNS, HOURS, PRIMARY_KEY

REQUIRED_NOT_NULL = [
    "city_id",
    "store_id",
    "first_category_id",
    "product_id",
    "dt",
    "sale_amount",
    "hours_sale",
    "hours_stock_status",
    "stock_hour6_22_cnt",
]


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str  # "hard" (row quarantine or abort) or "soft" (reported)
    passed: bool
    n_failed: int
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _list_len(series: pd.Series) -> np.ndarray:
    return np.array([len(x) if isinstance(x, (list, tuple, np.ndarray)) else -1 for x in series])


def validate_raw(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[CheckResult]]:
    results: list[CheckResult] = []
    missing_cols = [c for c in FRN_COLUMNS if c not in df.columns]
    results.append(
        CheckResult("schema_columns", "hard", not missing_cols, len(missing_cols), f"missing={missing_cols}")
    )
    if missing_cols:
        raise ValueError(f"raw data is missing required columns: {missing_cols}")

    work = df.reset_index(drop=True).copy()
    reasons = pd.Series([""] * len(work), dtype=object)

    def flag(mask: np.ndarray, reason: str, name: str) -> None:
        mask = np.asarray(mask, dtype=bool)
        n = int(mask.sum())
        results.append(CheckResult(name, "hard", n == 0, n, f"rows quarantined with reason '{reason}'"))
        reasons[mask & (reasons == "").to_numpy()] = reason

    nulls = work[REQUIRED_NOT_NULL].isna().any(axis=1).to_numpy()
    flag(nulls, "null_required_field", "not_null_required")
    flag(_list_len(work["hours_sale"]) != HOURS, "hours_sale_length", "hours_sale_length_24")
    flag(_list_len(work["hours_stock_status"]) != HOURS, "stock_status_length", "stock_status_length_24")
    sale = pd.to_numeric(work["sale_amount"], errors="coerce").to_numpy()
    flag(~np.isfinite(sale) | (sale < 0), "negative_or_nonfinite_sale", "sale_amount_nonnegative")

    def bad_status(x: object) -> bool:
        return not isinstance(x, (list, tuple, np.ndarray)) or any(v not in (0, 1) for v in x)

    flag(work["hours_stock_status"].map(bad_status).to_numpy(), "stock_status_values", "stock_status_binary")
    disc = pd.to_numeric(work["discount"], errors="coerce")
    flag(((disc <= 0) | (disc > 1)).to_numpy(), "discount_out_of_range", "discount_in_(0,1]")

    dup = work.duplicated(subset=PRIMARY_KEY, keep="first").to_numpy()
    n_dup = int(dup.sum())
    results.append(CheckResult("primary_key_unique", "hard", n_dup == 0, n_dup, f"key={PRIMARY_KEY}"))
    reasons[dup & (reasons == "").to_numpy()] = "duplicate_primary_key"

    bad = (reasons != "").to_numpy()
    quarantine = work[bad].assign(reason=reasons[bad].to_numpy())
    clean = work[~bad].copy()

    imputed = clean["discount"].isna()
    clean["discount_imputed"] = imputed.astype(np.int8)
    clean.loc[imputed, "discount"] = 1.0
    results.append(
        CheckResult(
            "discount_imputation", "soft", True, int(imputed.sum()), "missing discount set to 1.0 and flagged"
        )
    )
    results.extend(consistency_checks(clean))
    return clean, quarantine, results


def consistency_checks(clean: pd.DataFrame) -> list[CheckResult]:
    out: list[CheckResult] = []
    status = np.array(clean["hours_stock_status"].tolist(), dtype=np.int32)
    cnt = clean["stock_hour6_22_cnt"].to_numpy()
    match_21 = float(np.mean(status[:, 6:22].sum(axis=1) == cnt)) if len(cnt) else 1.0
    match_22 = float(np.mean(status[:, 6:23].sum(axis=1) == cnt)) if len(cnt) else 1.0
    out.append(
        CheckResult(
            "stock_count_matches_hours_6_21",
            "soft",
            match_21 >= 0.99,
            int(round((1 - match_21) * len(cnt))),
            f"match rate 6..21={match_21:.4f}, 6..22={match_22:.4f}",
        )
    )
    hours = np.array(clean["hours_sale"].tolist(), dtype=float)
    sale = clean["sale_amount"].to_numpy(dtype=float)
    rel = np.abs(hours.sum(axis=1) - sale) / np.maximum(np.abs(sale), 1e-9)
    ok = float(np.mean((rel < 1e-3) | (np.abs(hours.sum(axis=1) - sale) < 1e-6)))
    out.append(
        CheckResult(
            "sale_amount_equals_hourly_sum",
            "soft",
            ok >= 0.99,
            int(round((1 - ok) * len(sale))),
            f"agreement rate={ok:.4f}",
        )
    )
    per_series = clean.groupby(["store_id", "product_id"])["dt"].nunique()
    expected = clean["dt"].nunique()
    incomplete = int((per_series < expected).sum())
    out.append(
        CheckResult(
            "series_date_completeness",
            "soft",
            incomplete == 0,
            incomplete,
            f"{incomplete} of {len(per_series)} series miss at least one of {expected} dates",
        )
    )
    stockout_share = float(np.mean(cnt > 0)) if len(cnt) else 0.0
    out.append(
        CheckResult(
            "stockout_day_share",
            "soft",
            True,
            0,
            f"share of series-days with any stockout hour={stockout_share:.3f}",
        )
    )
    max_dt = str(clean["dt"].max()) if len(clean) else "none"
    out.append(CheckResult("freshness_max_event_date", "soft", True, 0, f"latest event date={max_dt}"))
    return out


def stock_count_hours(results: list[CheckResult]) -> tuple[int, int]:
    """Pick the stock-count hour window supported by the data (defaults to 6..21)."""
    for r in results:
        if r.name == "stock_count_matches_hours_6_21":
            parts = dict(p.split("=") for p in r.detail.replace("match rate ", "").split(", "))
            if float(parts["6..22"]) > float(parts["6..21"]):
                return 6, 23
    return 6, 22
