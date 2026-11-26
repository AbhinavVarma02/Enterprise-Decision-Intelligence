"""Generate the result tables in docs/BENCHMARK_FINDINGS.md from the committed artifacts.

Usage:
    python scripts/findings_tables.py            # print the tables
    python scripts/findings_tables.py --write    # replace the generated block in docs/BENCHMARK_FINDINGS.md

Only the block between the GENERATED markers is replaced; the narrative around it is written by hand
and must be checked against these tables.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "BENCHMARK_FINDINGS.md"
BEGIN = "<!-- GENERATED: scripts/findings_tables.py (do not edit by hand) -->"
END = "<!-- END GENERATED -->"

COND = {"normal": "Normal operations", "unreliable": "Unreliable data", "disruption": "Held-out disruptions"}
POLICY = {
    "P1": "P1 base-stock rule",
    "P2": "P2 point forecast + MILP",
    "P3": "P3 quantiles + expected-cost MILP",
    "P4": "P4 quantiles + mean-CVaR MILP",
    "P5a": "P5a validator over P3",
    "P5b": "P5b validator over P4",
    "ORACLE": "Oracle (hindsight bound)",
}
ABLATION = {
    "P5a_no_stockout_aware": "P5a with P3 forecasting from observed sales (no stockout-aware target)",
    "P5a_no_voi": "Validator without value of information (investigations become escalations)",
    "P5a_no_escalation": "Validator without escalation (escalations execute the validator's hedge or the candidate)",
    "P5a_no_risk_review": "Reviewer re-plans for expected cost instead of mean-CVaR",
    "P5a_untuned": "Validator with default soft thresholds (not tuned)",
    "P3_obs_vs_P3": "P3 on observed-sales forecasts, vs P3",
    "no_validation_P3_vs_P5a": "P3 without validation, vs P5a",
}
MODEL = {
    "seasonal_naive": "Seasonal naive",
    "moving_average": "Moving average (weekday-adjusted)",
    "lgbm_point": "LightGBM point",
    "lgbm_quantile_observed": "LightGBM quantiles, observed sales",
    "lgbm_quantile_recovered": "LightGBM quantiles, stockout-aware",
    "lgbm_quantile_recovered_nopromo": "Stockout-aware, no promotion inputs",
}


def usd(x: float) -> str:
    return f"${x:,.2f}"


def sgn(x: float, d: int = 2) -> str:
    return f"{x:+.{d}f}".replace("-", "−")


def pct(x: float | None, d: int = 1, signed: bool = False) -> str:
    if x is None:
        return "n/a"
    v = 100 * x
    if round(v, d) == 0:
        return f"{0:.{d}f}%"
    return (f"{v:+.{d}f}" if signed else f"{v:.{d}f}").replace("-", "−") + "%"


def ci(v: dict[str, Any], rel: bool = False) -> str:
    if rel:
        return f"{pct(v['relative_diff'], 2, True)} ({pct(v['relative_lo'], 2, True)} to {pct(v['relative_hi'], 2, True)})"
    d = v.get("diff_cost_per_day", v)
    return f"{sgn(d['mean'])} ({sgn(d['lo'])} to {sgn(d['hi'])})"


def tables(root: Path) -> str:
    s = json.loads((root / "artifacts" / "benchmark" / "summary.json").read_text())
    sec = json.loads((root / "artifacts" / "benchmark" / "secondary_cloud.json").read_text())
    fm = json.loads((root / "artifacts" / "forecast" / "metrics.json").read_text())
    m = s["meta"]
    out: list[str] = [BEGIN, ""]
    out.append(
        f"Run `{m['run_id']}` (code `{m['git_sha']}`), data source `{m['data_source']}`, {m['n_series']} store-products, "
        f"{m['realizations']} realizations per condition, test days {m['window'][0]} to {m['window'][1]}, "
        f"{m['n_decisions']:,} simulated decisions in {m['runtime_seconds'] / 60:.0f} minutes on 2 CPU cores. "
        f"Tuned on days 77 to 90: base-stock z = {m['tuning']['z']}, CVaR weight = {m['tuning']['lambda']}, "
        f"validator soft-threshold scale = {m['tuning']['validator_soft_scale']}."
    )
    inv = m.get("harness_invariants")
    if inv:
        out[-1] += (
            f" Harness invariant: {inv['replanned_orders_checked']:,} re-planned orders checked, "
            f"{inv['hard_breaches_after_replan']} hard breaches."
        )
    out.append("")
    out.append("### Policy results by condition")
    out.append("")
    out.append(
        "Cost per store-product day includes procurement, holding, waste, lost sales with goodwill, and review and "
        "stock-count costs. Brackets: 95% cluster-bootstrap interval over store-products. Tail: average of the worst "
        "10% of store-product daily costs. Unsafe: share of executed orders that were unsafe by the protocol's definition."
    )
    for cond, label in COND.items():
        out += ["", f"**{label}**", ""]
        out.append(
            "| Policy | Cost per day | Tail (CVaR90) | Fill rate | Waste | Review and count cost per day | Unsafe executed | Hard breaches |"
        )
        out.append("|---|---|---|---|---|---|---|---|")
        for p, v in s["main"][cond].items():
            c = v["cost_per_series_day"]
            unsafe = v.get("unsafe_executed_rate")
            out.append(
                f"| {POLICY.get(p, p)} | {usd(c['mean'])} ({usd(c['lo'])} to {usd(c['hi'])}) | {usd(v['cvar90_series_cost_per_day'])} "
                f"| {pct(v['fill_rate'])} | {pct(v['waste_rate'])} | {usd(v['governance_cost_per_day'])} "
                f"| {'n/a' if unsafe is None else pct(unsafe, 2)} | {v.get('hard_violations', 0)} |"
            )
    out += ["", "### Paired comparisons", ""]
    out.append(
        "Same store-products, same demand paths and faults. Difference in cost per store-product day (first minus "
        "second); negative means the first policy is cheaper."
    )
    out += ["", "| Comparison | " + " | ".join(COND.values()) + " |", "|---|---|---|---|"]
    for key, label in [
        ("P5a_vs_P3", "P5a vs P3 (effect of validation)"),
        ("P5b_vs_P4", "P5b vs P4 (effect of validation)"),
        ("P4_vs_P3", "P4 vs P3 (mean-CVaR vs expected cost)"),
        ("P3_vs_P2", "P3 vs P2 (quantiles vs point forecast)"),
        ("P3_vs_P1", "P3 vs P1 (MILP vs tuned base-stock)"),
        ("P5b_vs_P3", "P5b vs P3"),
        ("P3_vs_ORACLE", "P3 vs oracle"),
    ]:
        out.append(f"| {label} | " + " | ".join(ci(s["paired"][c][key]) for c in COND) + " |")
    out += ["", "Relative differences for the validation comparisons:", ""]
    out += ["| Comparison | " + " | ".join(COND.values()) + " |", "|---|---|---|---|"]
    for key in ("P5a_vs_P3", "P5b_vs_P4"):
        out.append(
            f"| {key.replace('_vs_', ' vs ')} | "
            + " | ".join(ci(s["paired"][c][key], rel=True) for c in COND)
            + " |"
        )
    out += ["", "### Validator outcomes and detection", ""]
    out += [
        "| Condition | Policy | Recommend | Investigate | Defer | Escalate | Reject | Unsafe candidates | Caught | Safe candidates flagged |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cond, label in COND.items():
        for p in ("P5a", "P5b"):
            det = s["detection"][cond][p]
            o = det["outcomes"]
            n_safe = det["n_candidates"] - det["n_unsafe"]
            out.append(
                f"| {label} | {p} | {o.get('recommend', 0)} | {o.get('investigate', 0)} | {o.get('defer', 0)} | "
                f"{o.get('escalate', 0)} | {o.get('reject', 0)} | {det['n_unsafe']} | "
                f"{'n/a' if det['recall'] is None else pct(det['recall'], 0)} | "
                f"{pct(det['unnecessary_intervention_rate'], 1)} of {n_safe} |"
            )
    out += [
        "",
        "### Ablations",
        "",
        "Difference in cost per store-product day against full P5a unless stated.",
        "",
    ]
    out += ["| Variant | " + " | ".join(COND.values()) + " |", "|---|---|---|---|"]
    for key, label in ABLATION.items():
        cells = []
        for c in COND:
            v = s["ablations"][c].get(key)
            cells.append(ci(v) if v and v.get("diff_cost_per_day") else "n/a")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out += ["", "### Forecast accuracy versus decision cost (P3, normal operations)", ""]
    out += [
        "| Forecast | Decision cost per day | Pinball vs observed sales | WAPE vs observed | Bias vs observed | Pinball vs true demand |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(s["forecast_variants"], key=lambda r: r["decision_cost_per_day"]["mean"]):
        c = r["decision_cost_per_day"]
        lat = r.get("pinball_vs_latent")
        out.append(
            f"| {MODEL.get(r['model'], r['model'])} | {usd(c['mean'])} | {r['pinball_vs_observed']:.3f} | {pct(r['wape_vs_observed'])} "
            f"| {pct(r['bias_vs_observed'], 1, True)} | {'n/a' if lat is None else f'{lat:.3f}'} |"
        )
    out += ["", "### Sensitivity (unreliable data, P5a vs P3)", ""]
    out += ["| Assumption changed | Relative cost change (95% interval) |", "|---|---|"]
    for r in s["sensitivity"]:
        out.append(
            f"| {r['setting'].replace('_x', ' x').replace('_', ' ')} | {ci(r['P5a_vs_P3'], rel=True)} |"
        )
    db = s["demand_bounds"]["cost_per_day"]
    out += ["", "### Bounds on unobserved demand (normal operations)", ""]
    out.append(s["demand_bounds"]["note"])
    out += ["", "| Policy | Lower bound | Upper bound |", "|---|---|---|"]
    for p in db["lower"]:
        out.append(f"| {POLICY.get(p, p)} | {usd(db['lower'][p])} | {usd(db['upper'][p])} |")
    a = s["audit"]
    out += ["", "### External-recommendation audit", ""]
    out.append(
        f"{a['n_base_candidates']} benchmark candidates, each validated unchanged and with each injected fault "
        f"({a['n_evaluations']:,} validations). "
        f"{pct(a['overall_recall_on_unsafe'], 0)} of unsafe candidates were flagged; {pct(a['false_alarm_rate_on_safe'], 0)} of "
        "safe candidates were flagged too."
    )
    out += ["", "| Injected fault | Unsafe | Flagged | Unsafe flagged |", "|---|---|---|---|"]
    for k, v in a["by_fault"].items():
        rec = pct(v["recall_on_unsafe"], 0) if v["unsafe_share"] > 0 else "n/a"
        out.append(
            f"| {k.replace('_', ' ')} | {pct(v['unsafe_share'], 0)} | {pct(v['flagged_share'], 0)} | {rec} |"
        )
    out += ["", "### Risk-coverage (validated decisions, all conditions)", ""]
    out += [
        "| Soft-threshold scale | Automatic coverage | Coverage without approval routing | Unsafe among recommended |",
        "|---|---|---|---|",
    ]
    rows: dict[str, dict[str, Any]] = {}
    for r in s["risk_coverage"]:
        rows.setdefault(str(r["threshold_scale"]), {})[str(r["include_approval_routing"])] = r
    for scale, r in rows.items():
        out.append(
            f"| {scale} | {pct(r['True']['coverage'])} | {pct(r['False']['coverage'])} | {pct(r['True']['unsafe_rate_among_recommended'], 2)} |"
        )
    out += ["", "### Second domain: cloud capacity (synthetic)", ""]
    sm = sec["meta"]
    out.append(
        f"{sm['n_services']} services, weeks {sm['weeks'][0]} to {sm['weeks'][1]}. Cost per service-day."
    )
    pols = list(next(iter(sec["results"].values())).keys())
    out += ["", "| Policy | " + " | ".join(COND.values()) + " |", "|---|---|---|---|"]
    for p in pols:
        out.append(
            f"| {p.replace('_', ' ')} | "
            + " | ".join(usd(sec["results"][c][p]["cost_per_service_day"]["mean"]) for c in COND)
            + " |"
        )
    if "paired" in sec:
        out += ["", "| Paired | " + " | ".join(COND.values()) + " |", "|---|---|---|---|"]
        for key in next(iter(sec["paired"].values())):
            out.append(
                f"| {key.replace('_', ' ')} | "
                + " | ".join(ci(sec["paired"][c][key], rel=True) for c in COND)
                + " |"
            )
    st = fm["stage_B"]
    out += ["", "### Forecast evaluation (final stage, days 91 to 97)", ""]
    out += [
        "| Model | WAPE, in-stock days | Bias, in-stock days | Pinball, all days | 80% coverage | Pinball vs true demand | Bias vs true demand | 80% coverage vs true demand |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for k, v in st["models"].items():
        lat = v.get("vs_latent_all") or {}
        out.append(
            f"| {MODEL.get(k, k)} | {pct(v['vs_observed_instock']['wape'])} | {pct(v['vs_observed_instock']['bias'], 1, True)} "
            f"| {v['vs_observed_all']['pinball']:.3f} | {pct(v['vs_observed_all']['coverage80'])} "
            f"| {lat.get('pinball', float('nan')):.3f} | {pct(lat.get('bias'), 1, True)} | {pct(lat.get('coverage80'))} |"
        )
    ce = fm["censoring_experiment"]
    out += [
        "",
        f"Controlled censoring experiment ({ce['design']}; {ce['observed_as_demand']['n']:,} days):",
        "",
    ]
    out += ["| Estimate | Mean absolute error | Bias |", "|---|---|---|"]
    out.append(
        f"| Observed sales as demand | {ce['observed_as_demand']['mae']:.2f} | {sgn(ce['observed_as_demand']['bias_pct'], 1)}% |"
    )
    out.append(
        f"| Hourly-profile recovery | {ce['profile_recovery']['mae']:.2f} | {sgn(ce['profile_recovery']['bias_pct'], 1)}% |"
    )
    out += ["", END]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    block = tables(ROOT)
    if not args.write:
        print(block)
        return
    text = DOC.read_text()
    if BEGIN not in text or END not in text:
        raise SystemExit(f"markers not found in {DOC}")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    DOC.write_text(head + block + tail)
    print(f"updated {DOC}")


if __name__ == "__main__":
    main()
