"""Loader for the real FreshRetailNet-50K parquet files (CC BY 4.0, Dingdong-Inc).

Download with `scripts/download_freshretailnet.py`, which records the resolved dataset revision and
file checksums in `data/raw/freshretailnet/PROVENANCE.json`.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from edi.ingestion.schema import FRN_COLUMNS

DATASET_REPO = "Dingdong-Inc/FreshRetailNet-50K"
ATTRIBUTION = (
    "FreshRetailNet-50K by Dingdong-Inc (https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K), "
    "licensed CC BY 4.0. Wang et al., arXiv:2505.16319."
)


def find_split_files(raw_dir: Path) -> dict[str, list[Path]]:
    files = sorted(raw_dir.rglob("*.parquet"))
    out: dict[str, list[Path]] = {"train": [], "eval": []}
    for f in files:
        name = f.stem.lower()
        if name == "eval" or name.startswith("eval-"):
            out["eval"].append(f)
        elif name == "train" or name.startswith("train-"):
            out["train"].append(f)
    return out


def available(raw_dir: Path) -> bool:
    files = find_split_files(raw_dir)
    return bool(files["train"]) and bool(files["eval"])


def select_series(stats: pd.DataFrame, n_series: int, seed: int) -> pd.DataFrame:
    """Select deterministically within historical stockout-day share terciles."""
    if n_series >= len(stats):
        return stats[["store_id", "product_id"]]
    stats["tercile"] = pd.qcut(stats["stockout"].rank(method="first"), 3, labels=False)
    rng = np.random.default_rng(seed)
    per = [n_series // 3 + (1 if i < n_series % 3 else 0) for i in range(3)]
    picks = []
    for tercile, k in zip(range(3), per):
        group = stats[stats["tercile"] == tercile]
        idx = rng.choice(len(group), size=min(k, len(group)), replace=False)
        picks.append(group.iloc[np.sort(idx)])
    return pd.concat(picks)[["store_id", "product_id"]]


def load(
    raw_dir: Path, n_series: int, seed: int, target_median_daily_units: float, selection_end_day: int
) -> tuple[pd.DataFrame, dict]:
    files = find_split_files(raw_dir)
    if not files["train"] or not files["eval"]:
        raise FileNotFoundError(f"FreshRetailNet-50K parquet files not found under {raw_dir}")
    with duckdb.connect(config={"threads": 2}) as con:
        for split, paths in files.items():
            con.read_parquet([str(f) for f in paths]).create_view(split)
        train_dates = con.sql("SELECT DISTINCT dt FROM train ORDER BY dt").df()["dt"]
        eval_dates = con.sql("SELECT DISTINCT dt FROM eval ORDER BY dt").df()["dt"]
        expected = pd.date_range(pd.Timestamp(train_dates.iloc[0]), periods=97).strftime("%Y-%m-%d")
        if train_dates.tolist() != expected[:90].tolist() or eval_dates.tolist() != expected[90:].tolist():
            raise ValueError("official partitions must cover consecutive days 1–90 (train) and 91–97 (eval)")
        if not 1 <= selection_end_day <= len(train_dates):
            raise ValueError("the subset and volume scale must be fitted within the training partition")
        stats = con.execute(
            """SELECT store_id, product_id, avg(CAST(stock_hour6_22_cnt > 0 AS INTEGER)) AS stockout,
                      avg(sale_amount) AS mean_sales
               FROM train WHERE dt <= ? GROUP BY store_id, product_id ORDER BY store_id, product_id""",
            [train_dates.iloc[selection_end_day - 1]],
        ).df()
        keep = select_series(stats, n_series, seed)
        con.register("selected_series", keep)
        columns = ", ".join(f"raw.{name}" for name in FRN_COLUMNS)
        raw = pd.concat(
            [
                con.sql(
                    f"SELECT {columns}, '{split}' AS source_split "
                    f"FROM {split} raw SEMI JOIN selected_series USING (store_id, product_id)"
                ).df()
                for split in ("train", "eval")
            ],
            ignore_index=True,
        )
    # Global volume rescale. sale_amount is normalized by one global coefficient, so a single factor
    # preserves relative structure while giving unit economics a plausible scale (assumption).
    series_mean = stats.merge(keep, on=["store_id", "product_id"])["mean_sales"]
    median = float(series_mean.median()) if len(series_mean) else 1.0
    factor = target_median_daily_units / median if median > 0 else 1.0
    raw["sale_amount"] = raw["sale_amount"] * factor
    raw["hours_sale"] = raw["hours_sale"].map(
        lambda xs: np.asarray(xs, dtype=float) * factor, na_action="ignore"
    )
    info = {
        "data_source": "freshretailnet_50k",
        "attribution": ATTRIBUTION,
        "files": [p.relative_to(raw_dir).as_posix() for p in files["train"] + files["eval"]],
        "n_series_selected": int(len(keep)),
        "subset_seed": seed,
        "volume_scale_factor": factor,
        "selection_and_scale_days": [1, selection_end_day],
        "official_split_dates": {"train": [expected[0], expected[89]], "eval": [expected[90], expected[96]]},
        "volume_scale_note": "assumed global rescale so the median series has the configured mean daily units",
    }
    return raw, info
