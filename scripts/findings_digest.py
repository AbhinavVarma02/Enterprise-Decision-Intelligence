"""Print the headline numbers from the committed artifacts, for writing and checking the docs.

Usage: python scripts/findings_digest.py [artifacts_dir]

Reads artifacts/benchmark/summary.json, artifacts/benchmark/secondary_cloud.json and
artifacts/forecast/metrics.json. Prints plain text; never edits any document.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:+.{d}f}%"


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    s = json.loads((root / "benchmark" / "summary.json").read_text())
    m = s["meta"]
    print(
        f"run {m['run_id']} source={m['data_source']} series={m['n_series']} realizations={m['realizations']}"
    )
    print(
        f"decisions={m['n_decisions']} runtime_s={m['runtime_seconds']} window={m['window']} tuning={m['tuning']}"
    )
    for cond, pols in s["main"].items():
        print(f"\n== {cond}")
        for p, v in pols.items():
            c = v["cost_per_series_day"]
            print(
                f"  {p:7s} cost/day {c['mean']:.2f} [{c['lo']:.2f},{c['hi']:.2f}] cvar90 {v['cvar90_series_cost_per_day']:.1f} "
                f"fill {v['fill_rate']:.3f} waste {v['waste_rate']:.3f} gov {v['governance_cost_per_day']:.2f} "
                f"unsafe {v.get('unsafe_executed_rate')} hard {v.get('hard_violations')} outcomes {v.get('outcomes', '')}"
            )
        for k, v in s["paired"][cond].items():
            dd = v["diff_cost_per_day"]
            print(
                f"  paired {k:12s} diff/day {dd['mean']:+.2f} [{dd['lo']:+.2f},{dd['hi']:+.2f}] rel "
                f"{pct(v['relative_diff'], 2)} [{pct(v['relative_lo'], 2)},{pct(v['relative_hi'], 2)}]"
            )
        for k, v in s["ablations"][cond].items():
            if v and v.get("diff_cost_per_day"):
                dd = v["diff_cost_per_day"]
                print(f"  ablation {k:24s} {dd['mean']:+.2f} [{dd['lo']:+.2f},{dd['hi']:+.2f}]")
    print("\n== hypotheses")
    for h in s["hypotheses"]:
        print(f"  {h['id']} {h['verdict']}: {h['statement']}")
        print(f"     evidence: {json.dumps(h['evidence'])[:600]}")
    print("\n== forecast variants (normal)")
    for r in s["forecast_variants"]:
        c = r["decision_cost_per_day"]
        print(
            f"  {r['model']:34s} cost {c['mean']:.2f} [{c['lo']:.2f},{c['hi']:.2f}] pinball_obs {r['pinball_vs_observed']:.3f} "
            f"wape_obs {r['wape_vs_observed']:.3f} bias_obs {r['bias_vs_observed']:+.3f} pinball_lat {r.get('pinball_vs_latent')}"
        )
    print("\n== sensitivity (unreliable, P5a vs P3)")
    for r in s["sensitivity"]:
        v = r["P5a_vs_P3"]
        print(
            f"  {r['setting']:20s} {pct(v['relative_diff'], 2)} [{pct(v['relative_lo'], 2)},{pct(v['relative_hi'], 2)}]"
        )
    print("\n== demand bounds", json.dumps(s["demand_bounds"])[:500])
    a = s["audit"]
    print(
        f"\n== audit base={a['n_base_candidates']} evals={a['n_evaluations']} recall_unsafe={a['overall_recall_on_unsafe']:.3f} "
        f"false_alarm_safe={a['false_alarm_rate_on_safe']:.3f}"
    )
    for k, v in a["by_fault"].items():
        print(
            f"  {k:24s} unsafe {v['unsafe_share']:.2f} flagged {v['flagged_share']:.2f} recall {v.get('recall_on_unsafe')}"
        )
    print("\n== risk coverage (tuned scale", s["risk_coverage_tuned_scale"], ")")
    for r in s["risk_coverage"]:
        print(f"  {r}")
    print("\n== detection")
    for cond, v in s["detection"].items():
        print(f"  {cond}: {json.dumps(v)[:400]}")
    sec = root / "benchmark" / "secondary_cloud.json"
    if sec.exists():
        c = json.loads(sec.read_text())
        print("\n== secondary", json.dumps(c.get("meta", {}))[:300])
        for cond, pols in c["results"].items():
            print(
                f"  {cond}: "
                + ", ".join(f"{p} {v['cost_per_service_day']['mean']:.2f}" for p, v in pols.items())
            )
        print("  paired", json.dumps(c.get("paired", {}))[:600])
        print("  reuse", json.dumps(c.get("reuse", {}))[:400])
    f = json.loads((root / "forecast" / "metrics.json").read_text())
    st = f["stage_B"]
    print("\n== forecast metrics (stage B)", f.get("data_source"), st["forecast_targets"], st["recovery"])
    for k, v in st["models"].items():
        print(
            f"  {k:34s} wape_in {v['vs_observed_instock']['wape']:.3f} bias_in {v['vs_observed_instock']['bias']:+.3f} "
            f"pinball {v['vs_observed_all']['pinball']:.3f} cov80 {v['vs_observed_all']['coverage80']:.3f} latent {json.dumps(v.get('vs_latent_all'))}"
        )
    print("  censoring", json.dumps(f["censoring_experiment"])[:700])


if __name__ == "__main__":
    main()
