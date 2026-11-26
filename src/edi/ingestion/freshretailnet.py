"""Loader for the real FreshRetailNet-50K parquet files (CC BY 4.0, Dingdong-Inc).

Download with `scripts/download_freshretailnet.py`, which records the resolved dataset revision and
file checksums in `data/raw/freshretailnet/PROVENANCE.json`.
"""

from __future__ import annotations

from pathlib import Path

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
        name = f.as_posix().lower()
        if "eval" in name or "test" in name:
            out["eval"].append(f)
        elif "train" in name:
            out["train"].append(f)
    return out


def available(raw_dir: Path) -> bool:
    files = find_split_files(raw_dir)
    return bool(files["train"]) and bool(files["eval"])


def select_series(train: pd.DataFrame, n_series: int, seed: int) -> pd.DataFrame:
    """Deterministic subset stratified by stockout-day share terciles (keeps censored series)."""
    stats = (
        train.assign(stockout=(train["stock_hour6_22_cnt"] > 0).astype(float))
        .groupby(["store_id", "product_id"], as_index=False)["stockout"]
        .mean()
        .sort_values(["store_id", "product_id"])
    )
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
    raw_dir: Path, n_series: int, seed: int, target_median_daily_units: float
) -> tuple[pd.DataFrame, dict]:
    files = find_split_files(raw_dir)
    if not files["train"] or not files["eval"]:
        raise FileNotFoundError(f"FreshRetailNet-50K parquet files not found under {raw_dir}")
    cols = list(FRN_COLUMNS)
    train = pd.concat([pd.read_parquet(f, columns=cols) for f in files["train"]], ignore_index=True)
    eval_ = pd.concat([pd.read_parquet(f, columns=cols) for f in files["eval"]], ignore_index=True)
    keep = select_series(train, n_series, seed)
    train = train.merge(keep, on=["store_id", "product_id"])
    eval_ = eval_.merge(keep, on=["store_id", "product_id"])
    raw = pd.concat([train, eval_], ignore_index=True)
    # Global volume rescale. sale_amount is normalized by one global coefficient, so a single factor
    # preserves relative structure while giving unit economics a plausible scale (assumption).
    series_mean = raw.groupby(["store_id", "product_id"])["sale_amount"].mean()
    median = float(series_mean.median()) if len(series_mean) else 1.0
    factor = target_median_daily_units / median if median > 0 else 1.0
    raw["sale_amount"] = raw["sale_amount"] * factor
    raw["hours_sale"] = raw["hours_sale"].map(lambda xs: [float(x) * factor for x in xs])
    info = {
        "data_source": "freshretailnet_50k",
        "attribution": ATTRIBUTION,
        "files": [str(p) for p in files["train"] + files["eval"]],
        "n_series_selected": int(len(keep)),
        "subset_seed": seed,
        "volume_scale_factor": factor,
        "volume_scale_note": "assumed global rescale so the median series has the configured mean daily units",
    }
    return raw, info
