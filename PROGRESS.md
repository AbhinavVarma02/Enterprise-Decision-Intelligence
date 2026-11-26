# PROGRESS

Last updated: 2026-11-26 12:40 America/New_York

## Status

All build phases are complete on synthetic data. Two items are blocked by the environment, not by the code: running on the real FreshRetailNet-50K dataset (Hugging Face unreachable from the build machine) and deploying to Cloudflare Pages (no credentials). Both have exact commands in the README and `docs/DEPLOYMENT.md`.

| Area | State | Evidence |
|---|---|---|
| Data pipeline | Done | Schema-identical fixture, quality checks with quarantine, DuckDB curated layer; `tests/test_data_pipeline.py` |
| Forecasting | Done | Baselines, LightGBM point and quantile, stockout-aware target, conformal calibration, leakage test; `artifacts/forecast/metrics.json` |
| Simulation and optimization | Done | FIFO perishable simulator; cohort MILP (HiGHS) matches the simulator for shelf life of 3 days or more; brute-force tests |
| Validation engine | Done | G1 to G7, five outcomes, VOI, cost of inaction, prioritization, JSON Schemas |
| Benchmark | Done | Research run `research-76b4b4db2c95d63e`, 298,200 decisions, harness invariant passes; `docs/BENCHMARK_FINDINGS.md` |
| Second domain | Done | Cloud capacity on the same contract; `artifacts/benchmark/secondary_cloud.json` |
| Web app | Done | 7 pages, browser engine parity-tested (40 Vitest tests), 10 journey tests, 21 axe scans, 21 screenshots |
| Docs | Done | README, findings, architecture, protocol with 2 amendments, data model, security, deployment, design system, UI review, ADR 0001-0009, notices |
| CI | Written, not run on GitHub | `.github/workflows/ci.yml`; every step was run locally |
| Real data run | Blocked | huggingface.co unreachable here |
| Deployment | Blocked | No Cloudflare credentials; commands documented |

## Verification run on 2026-11-26

- `pytest -q`: 58 passed on Python 3.13 (pandas 3.1) and Python 3.10 (pandas 2.3).
- `ruff check`, `ruff format --check`, `mypy src`: clean.
- `npm run lint`, `npm run typecheck`, `npx vitest run` (40), `npm run build` (29 files, 0.95 MB), Playwright journeys (10), axe scans (21): all pass.
- `npm audit --omit=dev` and `pip-audit` on the installed environment: no known vulnerabilities.
- `edi run-all --config configs/ci.yaml`: completes in about 100 seconds.

## Headline results (synthetic)

Validation removed all hard-constraint breaches under unreliable data (177 to 0) and cut unsafe executed orders from 4.21% to 0.02%, but raised total cost by 0.67% (0.33% to 0.99%) because of review and stock-count costs; operating cost was unchanged. Mean-CVaR optimization was the cheapest policy. Stockout-aware forecasts beat the more "accurate" observed-sales model on decision cost. Details and negative results in `docs/BENCHMARK_FINDINGS.md`.

## Environment notes

- Build machine: Linux, 2 CPU cores, Python 3.13, Node 22. Research run takes about 105 minutes.
- The linked Windows machine has a Linux shell with Python 3.10; its copy of the repository is synced from here.
