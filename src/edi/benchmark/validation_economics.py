"""Incremental breach-cost sensitivity and an independently seeded routing experiment."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

from edi.benchmark.experiments import Cell, PolicySpec, run_cells
from edi.benchmark.report import detection, harness_invariants, latest_run, paired, policy_metrics
from edi.core import artifact_path, config_hash, read_json, write_json
from edi.pipeline import load_panel

COMPONENTS = ("contract_penalty", "administrative_rework", "incremental_sourcing", "other_disruption")
ASSUMPTIONS = ((0, 0, 0, 0), (0, 5, 0, 0), (0, 5, 3, 2), (5, 5, 10, 5), (10, 10, 20, 10))


def breach_economics(summary: dict[str, Any]) -> dict[str, Any]:
    """Reprice existing decisions once per breached submission, with no change in behavior."""
    baseline, validated = (summary["main"]["unreliable"][p] for p in ("P3", "P5a"))
    n = sum(baseline["outcomes"].values())
    if n != sum(validated["outcomes"].values()):
        raise ValueError("breach sensitivity requires matched decision-day denominators")
    cost = summary["paired"]["unreliable"]["P5a_vs_P3"]["diff_cost_per_day"]["mean"]
    # Legacy summaries recorded the rate and total constraint flags, but omitted the event count.
    baseline_breaches, validated_breaches = (
        p.get("hard_breach_decisions", round(p["hard_violation_rate"] * n)) for p in (baseline, validated)
    )
    avoided = baseline_breaches - validated_breaches
    return {
        "source_run": summary["meta"]["run_id"],
        "data_source": summary["meta"]["data_source"],
        "decision_days_per_policy": n,
        "baseline_breached_submissions": baseline_breaches,
        "validated_breached_submissions": validated_breaches,
        "base_delta_per_day": cost,
        "base_delta_total": cost * n,
        "break_even_per_breached_submission": max(0.0, cost * n / avoided) if avoided > 0 else None,
        "sensitivity": [
            {
                "component_assumptions": dict(zip(COMPONENTS, amounts)),
                "assumed_increment_per_breached_submission": sum(amounts),
                "validated_cost_minus_baseline_per_day": cost - sum(amounts) * avoided / n,
            }
            for amounts in ASSUMPTIONS
        ],
    }


def run_selective(cfg: dict[str, Any], jobs: int) -> dict[str, Any]:
    """Evaluate a fixed optional-review screen in new, policy-matched worlds."""
    manifest = read_json(latest_run(cfg) / "manifest.json")
    if manifest["config_hash"] != config_hash(cfg):
        raise ValueError("selective experiment requires the main run for this configuration")
    tuned = manifest["tuning"]["validator_soft_scale"]
    replay = deepcopy(cfg)
    replay["benchmark"]["seed"] += 1_000_003
    seed = replay["benchmark"]["seed"]
    B = cfg["benchmark"]["bootstrap_resamples"]
    panel_idx = {series: i for i, series in enumerate(load_panel(cfg).series_ids)}
    idx = np.array([panel_idx[s] for s in manifest["series_ids"]])
    conditions = ("normal", "unreliable", "disruption")
    specs = (
        PolicySpec("P3", "saa"),
        PolicySpec("P5a", "validated", wrapped="saa"),
        PolicySpec("P5a_selective", "validated", wrapped="saa", selective_review=True),
    )
    cells = [
        Cell("selective", "test", condition, r, spec, vscale=tuned)
        for condition in conditions
        for r in range(manifest["realizations"])
        for spec in specs
    ]
    totals, decisions, _ = run_cells(replay, cells, idx, jobs)
    result: dict[str, Any] = {
        "source_run": manifest["run_id"],
        "data_source": manifest["data_source"],
        "seed": seed,
        "decisions": len(decisions),
        "harness_invariants": harness_invariants(decisions),
        "conditions": {},
    }
    for condition in conditions:
        t = totals[totals["condition"] == condition]
        d = decisions[decisions["condition"] == condition]
        result["conditions"][condition] = {
            "paired_selective_vs_p5a": paired(t, "P5a_selective", "P5a", B, seed),
            "policies": {
                p.pid: policy_metrics(t[t["policy"] == p.pid], d[d["policy"] == p.pid], B, seed)
                for p in specs
            },
            "detection": {p.pid: detection(d[d["policy"] == p.pid]) for p in specs if p.kind == "validated"},
        }
    write_json(artifact_path(cfg, "benchmark", "selective_validation.json"), result)
    return result
