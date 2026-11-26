"""Data pipeline: raw -> validated/quarantined -> staged -> curated (DuckDB + Parquet).

Each stage is idempotent: it is skipped when the manifest shows the same input hash and the outputs
exist. `force=True` re-runs everything.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from edi.core import (
    Manifest,
    config_hash,
    get_logger,
    hash_files,
    log_event,
    read_json,
    repo_path,
    utc_now,
    write_json,
    write_parquet,
)
from edi.data_quality.checks import stock_count_hours, validate_raw
from edi.ingestion import freshretailnet, synthetic
from edi.ingestion.schema import CATEGORY_PROFILES, HOURS, profile_for_category

log = get_logger("edi.pipeline")


@dataclass
class Layout:
    root: Path
    raw_real_override: Path | None = None

    @property
    def raw_synthetic(self) -> Path:
        return self.root / "raw" / "synthetic"

    @property
    def raw_real(self) -> Path:
        return self.raw_real_override or self.root / "raw" / "freshretailnet"

    @property
    def staged(self) -> Path:
        return self.root / "staged" / "series_day.parquet"

    @property
    def quarantine(self) -> Path:
        return self.root / "quarantine" / "rejected.parquet"

    @property
    def curated(self) -> Path:
        return self.root / "curated" / "series_day.parquet"

    @property
    def series_dim(self) -> Path:
        return self.root / "curated" / "series_dim.parquet"

    @property
    def duckdb(self) -> Path:
        return self.root / "edi.duckdb"

    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def dq_report(self) -> Path:
        return self.root / "curated" / "data_quality.json"


def layout(cfg: dict[str, Any]) -> Layout:
    raw_real = cfg["data"].get("raw_freshretailnet_dir")
    return Layout(repo_path(cfg["data"]["dir"]), repo_path(raw_real) if raw_real else None)


def resolve_source(cfg: dict[str, Any]) -> str:
    source = cfg["data"].get("source", "auto")
    if source == "auto":
        return "freshretailnet" if freshretailnet.available(layout(cfg).raw_real) else "synthetic"
    if source not in ("synthetic", "freshretailnet"):
        raise ValueError(f"unknown data source {source}")
    return str(source)


def _ensure_raw(cfg: dict[str, Any], lay: Layout, source: str, force: bool) -> list[Path]:
    if source == "synthetic":
        sc = cfg["data"]["synthetic"]
        prov_path = lay.raw_synthetic / "PROVENANCE.json"
        want = {"n_series": sc["n_series"], "n_stores": sc["n_stores"], "seed": sc["seed"]}
        current = read_json(prov_path)["params"] if prov_path.exists() else {}
        if force or any(current.get(k) != v for k, v in want.items()):
            synthetic.write_fixture(lay.raw_synthetic, **want)
            log_event(log, "synthetic fixture written", **want)
        return sorted(lay.raw_synthetic.glob("*.parquet"))
    files = freshretailnet.find_split_files(lay.raw_real)
    provenance = lay.raw_real / "PROVENANCE.json"
    return files["train"] + files["eval"] + ([provenance] if provenance.exists() else [])


def run(cfg: dict[str, Any], force: bool = False) -> dict[str, Any]:
    lay = layout(cfg)
    source = resolve_source(cfg)
    raw_files = _ensure_raw(cfg, lay, source, force)
    manifest = Manifest(lay.manifest)
    fit_end = cfg["windows"]["a_fit_end"]
    input_hash = (
        hash_files(raw_files)
        + ":"
        + config_hash({"data": cfg["data"], "source": source, "real_selection_end_day": fit_end})
    )
    if not force and manifest.is_current("pipeline", input_hash):
        log_event(log, "pipeline up to date, skipping", input_hash=input_hash)
        return dict(read_json(lay.dq_report))

    if source == "synthetic":
        raw = pd.concat(
            [pd.read_parquet(lay.raw_synthetic / f) for f in ("train.parquet", "eval.parquet")],
            ignore_index=True,
        )
        info: dict[str, Any] = read_json(lay.raw_synthetic / "PROVENANCE.json")
        data_source = "synthetic_fixture"
    else:
        fc = cfg["data"]["freshretailnet"]
        prov = lay.raw_real / "PROVENANCE.json"
        download = read_json(prov) if prov.exists() else {}
        if fc.get("revision") and download.get("revision") != fc["revision"]:
            raise ValueError(f"expected FreshRetailNet revision {fc['revision']} in {prov}")
        raw, info = freshretailnet.load(
            lay.raw_real, fc["n_series"], fc["subset_seed"], fc["target_median_daily_units"], fit_end
        )
        if download:
            info["download_provenance"] = download
        data_source = "freshretailnet_50k"

    clean, quarantine, results = validate_raw(raw)
    lo, hi = (6, 22) if source == "freshretailnet" else stock_count_hours(results)
    ingested_at = utc_now()
    dates = pd.to_datetime(clean["dt"])
    start = dates.min()
    clean["series_id"] = "s" + clean["store_id"].astype(str) + "_p" + clean["product_id"].astype(str)
    clean["day_index"] = ((dates - start).dt.days + 1).astype(int)
    clean["split"] = (
        clean.pop("source_split")
        if source == "freshretailnet"
        else np.where(clean["day_index"] <= 90, "train", "eval")
    )
    clean["data_source"] = data_source
    clean["ingested_at"] = ingested_at
    clean = clean.sort_values(["series_id", "day_index"]).reset_index(drop=True)
    n_days = int(clean["day_index"].max())

    write_parquet(clean, lay.staged)
    write_parquet(quarantine.astype({"hours_sale": object, "hours_stock_status": object}), lay.quarantine)

    lay.duckdb.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = lay.duckdb.with_suffix(".tmp.duckdb")
    if tmp_db.exists():
        tmp_db.unlink()
    con = duckdb.connect(str(tmp_db))
    try:
        con.execute(f"CREATE TABLE staged AS SELECT * FROM read_parquet('{lay.staged.as_posix()}')")
        sql = resources.files("edi").joinpath("sql/curated.sql").read_text(encoding="utf-8")
        sql = sql.format(n_days=n_days, lo=lo + 1, hi=hi)
        con.execute(sql)
        series_day = con.execute("SELECT * FROM series_day").df()
        series_dim = con.execute("SELECT * FROM series_dim ORDER BY series_id").df()
        daily = con.execute("SELECT * FROM dq_daily_summary").df()
    finally:
        con.close()
    tmp_db.replace(lay.duckdb)

    ordered = sorted(series_dim["first_category_id"].unique().tolist())
    series_dim["profile"] = [profile_for_category(int(c), ordered) for c in series_dim["first_category_id"]]
    write_parquet(series_day, lay.curated)
    write_parquet(series_dim, lay.series_dim)

    report = {
        "data_source": data_source,
        "ingested_at": ingested_at,
        "rows_raw": int(len(raw)),
        "rows_clean": int(len(clean)),
        "rows_quarantined": int(len(quarantine)),
        "quarantine_reasons": quarantine["reason"].value_counts().to_dict() if len(quarantine) else {},
        "n_series": int(series_dim.shape[0]),
        "n_days": n_days,
        "date_range": [str(start.date()), str((start + pd.Timedelta(days=n_days - 1)).date())],
        "stock_count_hours": [lo, hi - 1],
        "checks": [r.to_dict() for r in results],
        "daily": daily.assign(dt=daily["dt"].astype(str)).to_dict(orient="records"),
        "profiles": series_dim["profile"].value_counts().to_dict(),
        "source_info": {k: v for k, v in info.items() if k not in ("columns",)},
    }
    write_json(lay.dq_report, report)
    manifest.record(
        "pipeline",
        input_hash,
        [lay.staged, lay.curated, lay.series_dim, lay.duckdb, lay.dq_report],
        rows=int(len(clean)),
        data_source=data_source,
    )
    log_event(log, "pipeline complete", rows=len(clean), quarantined=len(quarantine), source=data_source)
    return report


# ---------------------------------------------------------------- panel access


@dataclass
class Panel:
    """Dense (series x day) arrays built from the curated layer. Day d is column d-1."""

    series_ids: list[str]
    dates: list[str]
    profile: list[str]
    category: np.ndarray
    store: np.ndarray
    sales: np.ndarray  # NaN where the row was missing or quarantined
    hours_sale: np.ndarray  # (S, D, 24)
    status: np.ndarray  # (S, D, 24) 1 = out of stock
    stockout_hours: np.ndarray
    discount: np.ndarray
    activity: np.ndarray
    holiday: np.ndarray
    temp: np.ndarray
    precip: np.ndarray
    humidity: np.ndarray
    wind: np.ndarray
    is_missing: np.ndarray
    data_source: str
    latent: np.ndarray | None = None  # synthetic ground truth only

    @property
    def n_series(self) -> int:
        return len(self.series_ids)

    @property
    def n_days(self) -> int:
        return len(self.dates)

    def subset(self, idx: np.ndarray) -> Panel:
        def take(a: np.ndarray | None) -> np.ndarray | None:
            return None if a is None else a[idx]

        return Panel(
            series_ids=[self.series_ids[i] for i in idx],
            dates=self.dates,
            profile=[self.profile[i] for i in idx],
            category=self.category[idx],
            store=self.store[idx],
            sales=self.sales[idx],
            hours_sale=self.hours_sale[idx],
            status=self.status[idx],
            stockout_hours=self.stockout_hours[idx],
            discount=self.discount[idx],
            activity=self.activity[idx],
            holiday=self.holiday[idx],
            temp=self.temp[idx],
            precip=self.precip[idx],
            humidity=self.humidity[idx],
            wind=self.wind[idx],
            is_missing=self.is_missing[idx],
            data_source=self.data_source,
            latent=take(self.latent),
        )


def load_panel(cfg: dict[str, Any]) -> Panel:
    lay = layout(cfg)
    sd = pd.read_parquet(lay.curated)
    dim = pd.read_parquet(lay.series_dim)
    report = read_json(lay.dq_report)
    series_ids = dim["series_id"].tolist()
    n_s, n_d = len(series_ids), int(sd["day_index"].max())
    sd = sd.sort_values(["series_id", "day_index"])
    if len(sd) != n_s * n_d:
        raise ValueError("curated series_day is not a complete grid")

    def grid(col: str, fill: float = np.nan) -> np.ndarray:
        return sd[col].astype(float).fillna(fill).to_numpy().reshape(n_s, n_d)

    def hours(col: str, fill: float) -> np.ndarray:
        vals = [
            x if isinstance(x, (list, np.ndarray)) and len(x) == HOURS else [fill] * HOURS for x in sd[col]
        ]
        return np.asarray(vals, dtype=float).reshape(n_s, n_d, HOURS)

    start = dt.date.fromisoformat(report["date_range"][0])
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(n_d)]
    latent = None
    if report["data_source"] == "synthetic_fixture":
        lat = pd.read_parquet(lay.raw_synthetic / "latent_demand.parquet")
        lat["series_id"] = "s" + lat["store_id"].astype(str) + "_p" + lat["product_id"].astype(str)
        lat["day_index"] = (pd.to_datetime(lat["dt"]) - pd.Timestamp(start)).dt.days + 1
        lat = lat.set_index(["series_id", "day_index"])["latent_daily"]
        idx = pd.MultiIndex.from_product([series_ids, range(1, n_d + 1)])
        latent = lat.reindex(idx).to_numpy(dtype=float).reshape(n_s, n_d)
    profiles = dim["profile"].tolist()
    if any(p not in CATEGORY_PROFILES for p in profiles):
        raise ValueError("unknown economics profile in series_dim")
    return Panel(
        series_ids=series_ids,
        dates=dates,
        profile=profiles,
        category=dim["first_category_id"].to_numpy(),
        store=dim["store_id"].to_numpy(),
        sales=grid("sale_amount"),
        hours_sale=hours("hours_sale", np.nan),
        status=hours("hours_stock_status", 0.0),
        stockout_hours=grid("stockout_hours", 0.0),
        discount=grid("discount", 1.0),
        activity=grid("activity_flag", 0.0),
        holiday=grid("holiday_flag", 0.0),
        temp=grid("avg_temperature"),
        precip=grid("precpt"),
        humidity=grid("avg_humidity"),
        wind=grid("avg_wind_level"),
        is_missing=grid("is_missing", 1.0).astype(bool),
        data_source=report["data_source"],
        latent=latent,
    )
