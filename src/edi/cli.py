"""Command-line interface: `edi <command> --config configs/dev.yaml`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from edi.core import get_logger, load_config, log_event

log = get_logger("edi.cli")


def _pipeline(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi import pipeline

    rep = pipeline.run(cfg, force=args.force)
    return {k: rep[k] for k in ("data_source", "rows_clean", "rows_quarantined", "n_series", "n_days")}


def _forecast(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi import pipeline
    from edi.forecasting import run as fr

    s = fr.run(cfg, pipeline.load_panel(cfg))
    return {"runtime_seconds": s["runtime_seconds"], "data_source": s["data_source"]}


def _benchmark(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi.benchmark.experiments import run_all

    m = run_all(cfg, n_jobs=args.jobs)
    return {k: m[k] for k in ("run_id", "n_decisions", "runtime_seconds", "tuning")}


def _report(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi.benchmark.report import build_report

    r = build_report(cfg)
    return {"summary": r["paths"]}


def _secondary(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi.domains.cloud_capacity import run_experiment

    r = run_experiment(cfg)
    return {"path": r["path"], "runtime_seconds": r["runtime_seconds"]}


def _selective(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi.benchmark.validation_economics import run_selective

    r = run_selective(cfg, args.jobs)
    return {k: r[k] for k in ("source_run", "seed", "decisions", "harness_invariants")}


def _export(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from edi.export.web import export_all, export_research_evidence

    if cfg["data"]["source"] == "freshretailnet":
        return export_research_evidence(cfg)
    return export_all(cfg)


def _run_all(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    out = {}
    for name, fn in (
        ("pipeline", _pipeline),
        ("forecast", _forecast),
        ("benchmark", _benchmark),
        ("report", _report),
        ("secondary", _secondary),
        ("export", _export),
    ):
        t0 = time.perf_counter()
        out[name] = fn(cfg, args)
        log_event(log, "stage complete", stage=name, seconds=round(time.perf_counter() - t0, 1))
    return out


COMMANDS = {
    "pipeline": _pipeline,
    "forecast": _forecast,
    "benchmark": _benchmark,
    "report": _report,
    "secondary": _secondary,
    "selective-validation": _selective,
    "export-web": _export,
    "run-all": _run_all,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="edi", description="Enterprise Decision Intelligence")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--config", default="configs/dev.yaml")
    parser.add_argument("--force", action="store_true", help="re-run stages even if inputs are unchanged")
    parser.add_argument("--jobs", type=int, default=2, help="worker processes for the benchmark")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    result = COMMANDS[args.command](cfg, args)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
