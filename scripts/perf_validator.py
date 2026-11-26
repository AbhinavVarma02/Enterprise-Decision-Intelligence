"""Measure validator latency on decision records saved by a benchmark run.

Usage: python scripts/perf_validator.py [--config configs/research.yaml] [--n 400]

Re-validates up to N saved (candidate, context) pairs from the latest run of the config, single
process, and prints p50, p95 and max wall-clock milliseconds per validation. Run it on an idle
machine; timings depend on the CPU.
"""

from __future__ import annotations

import argparse
import statistics
import time

from edi.benchmark.report import latest_run
from edi.core import load_config, read_json
from edi.export.web import validator_params
from edi.validation.engine import validate
from edi.validation.inventory import InventoryAdapter
from edi.validation.schema import AuthoritativeContext, DecisionCandidate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/research.yaml")
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()
    cfg = load_config(args.config)
    run = latest_run(cfg)
    manifest = read_json(run / "manifest.json")
    soft = float(manifest["tuning"].get("validator_soft_scale", 1.0))
    vp = validator_params(cfg, soft, int(cfg["benchmark"]["scenarios"]))
    samples = [s for s in read_json(run / "samples.json") if s.get("experiment") == "main"][: args.n]
    adapter = InventoryAdapter()
    times = []
    outcomes: dict[str, int] = {}
    for s in samples:
        cand = DecisionCandidate.model_validate(s["candidate"])
        ctx = AuthoritativeContext.model_validate(s["context"])
        t0 = time.perf_counter()
        rep = validate(cand, ctx, adapter, vp)
        times.append((time.perf_counter() - t0) * 1e3)
        outcomes[rep.outcome] = outcomes.get(rep.outcome, 0) + 1
    times.sort()
    p95 = times[int(0.95 * (len(times) - 1))]
    print(
        f"run {manifest['run_id']}: {len(times)} validations, scenarios {vp.n_scenarios}, "
        f"p50 {statistics.median(times):.1f} ms, p95 {p95:.1f} ms, max {times[-1]:.1f} ms; outcomes {outcomes}"
    )


if __name__ == "__main__":
    main()
