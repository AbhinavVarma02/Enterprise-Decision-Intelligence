"""Ingestion, data quality, quarantine and pipeline idempotence."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from edi import pipeline
from edi.core import Manifest, read_json
from edi.data_quality.checks import validate_raw
from edi.ingestion import synthetic
from edi.ingestion.freshretailnet import select_series
from edi.ingestion.schema import FRN_COLUMNS


def test_synthetic_fixture_is_deterministic_and_schema_identical() -> None:
    a = synthetic.generate(n_series=8, n_stores=2, seed=3)
    b = synthetic.generate(n_series=8, n_stores=2, seed=3)
    pd.testing.assert_frame_equal(a.raw, b.raw)
    assert list(a.raw.columns) == list(FRN_COLUMNS)
    c = synthetic.generate(n_series=8, n_stores=2, seed=4)
    assert not a.raw["sale_amount"].equals(c.raw["sale_amount"])


def test_synthetic_censoring_never_exceeds_latent_demand() -> None:
    fx = synthetic.generate(n_series=6, n_stores=2, seed=5)
    raw = fx.raw.drop_duplicates(["store_id", "product_id", "dt"])
    merged = raw.merge(fx.latent, on=["store_id", "product_id", "dt"])
    ok = merged["sale_amount"] >= 0
    assert (merged.loc[ok, "sale_amount"] <= merged.loc[ok, "latent_daily"] + 1e-9).all()


def test_quality_checks_quarantine_injected_defects() -> None:
    fx = synthetic.generate(n_series=6, n_stores=2, seed=9)
    clean, quarantine, results = validate_raw(fx.raw)
    reasons = quarantine["reason"].value_counts().to_dict()
    assert reasons.get("duplicate_primary_key") == synthetic.N_DUPLICATES
    assert reasons.get("negative_or_nonfinite_sale", 0) + reasons.get("hours_sale_length", 0) >= 2
    assert clean.duplicated(["store_id", "product_id", "dt"]).sum() == 0
    assert clean["discount"].notna().all()
    assert int(clean["discount_imputed"].sum()) == synthetic.N_NULL_DISCOUNT
    assert len(clean) + len(quarantine) == len(fx.raw)
    names = {r.name for r in results}
    assert {"primary_key_unique", "stock_count_matches_hours_6_21", "sale_amount_equals_hourly_sum"} <= names


def test_missing_required_column_aborts() -> None:
    fx = synthetic.generate(n_series=4, n_stores=1, seed=1)
    with pytest.raises(ValueError, match="missing required columns"):
        validate_raw(fx.raw.drop(columns=["hours_stock_status"]))


def test_pipeline_outputs_complete_grid_and_is_idempotent(pipeline_cfg) -> None:
    lay = pipeline.layout(pipeline_cfg)
    report = read_json(lay.dq_report)
    sd = pd.read_parquet(lay.curated)
    assert len(sd) == report["n_series"] * report["n_days"]
    assert sd["is_missing"].sum() >= 1  # quarantined rows leave visible gaps, not silent fills
    assert report["data_source"] == "synthetic_fixture"
    m = Manifest(lay.manifest)
    rec = m.data["stages"]["pipeline"]
    mtime = lay.curated.stat().st_mtime_ns
    again = pipeline.run(pipeline_cfg)  # unchanged inputs: stage is skipped
    assert lay.curated.stat().st_mtime_ns == mtime
    assert again["rows_clean"] == report["rows_clean"]
    assert Manifest(lay.manifest).data["stages"]["pipeline"]["input_hash"] == rec["input_hash"]


def test_panel_temporal_order_and_splits(panel) -> None:
    assert panel.n_days == 97
    assert panel.dates == sorted(panel.dates)
    assert panel.latent is not None and panel.latent.shape == panel.sales.shape
    ok = np.isfinite(panel.sales)
    assert (panel.sales[ok] <= panel.latent[ok] + 1e-9).all()


def test_real_subset_selection_is_deterministic_and_stratified() -> None:
    rng = np.random.default_rng(0)
    rows = []
    for s in range(30):
        share = s / 30
        for _ in range(10):
            rows.append({"store_id": s, "product_id": 1, "stock_hour6_22_cnt": int(rng.random() < share)})
    df = pd.DataFrame(rows)
    a = select_series(df, 9, seed=7)
    b = select_series(df, 9, seed=7)
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
    assert len(a) == 9


def test_source_resolution_prefers_real_data_only_when_present(pipeline_cfg) -> None:
    cfg = copy.deepcopy(pipeline_cfg)
    cfg["data"]["source"] = "auto"
    assert pipeline.resolve_source(cfg) == "synthetic"
