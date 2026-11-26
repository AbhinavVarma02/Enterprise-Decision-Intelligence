# Changelog

All notable changes. Dates are America/New_York.

## [Unreleased]

### Added
- 2026-11-25: Project continuity files, research log, competitive analysis, architecture with five-perspective review, ADR 0001-0008, frozen experiment protocol v1.0.
- 2026-11-25: Data pipeline (FreshRetailNet-50K downloader with provenance, schema-identical synthetic fixture, quality checks with quarantine, DuckDB curated layer).
- 2026-11-25: Forecasting: baselines, LightGBM point and quantile models, stockout-aware target via hourly-profile recovery, split-conformal calibration, two-stage chronological windows, leakage test, controlled censoring experiment.
- 2026-11-25: Perishable FIFO simulator, cohort-based scenario MILP (HiGHS) with MOQ, budget, capacity and mean-CVaR; brute-force and simulator-agreement tests.
- 2026-11-25: Independent validation engine (gates G1 to G7, five outcomes, value of verification and EVPI, cost of inaction, exception prioritization), JSON Schemas for the decision contract (ADR-0009).
- 2026-11-25: Decision Reliability Benchmark: common random numbers, three conditions, fault and disruption injection, policies P1 to P5b and a hindsight oracle, ablations, forecast variants, sensitivity, demand bounds, cluster bootstrap, risk-coverage curve, external-recommendation audit, hypothesis verdicts.
- 2026-11-25: Secondary domain (cloud capacity reservation) on the same contract and validator; mock ERP adapter.
- 2026-11-25: Static web app (React 19, TypeScript, Vite): overview, decision workspace, scenario studio, benchmark, data and reliability, decision history, methodology. Browser evaluator and validator parity-tested against Python golden fixtures. Hash-chained local decision log with schema-validated import and export.
- 2026-11-26: Responsive tables and charts for phones, methodology flow as an ordered list, skip link and off-canvas focus handling, contrast fix, UI review log.
- 2026-11-26: Security and threat model, data model, deployment guide, third-party notices, pinned dependency lock, CI workflow, findings digest script.

### Fixed
- 2026-11-25: Feature leakage (lags read the target day); found by the leakage test before any reported run.
- 2026-11-25: Approval-rule artifact at the end of the test window and missing validator threshold tuning (protocol amendment 1).
- 2026-11-26: Benchmark harness re-planned after a simulated stock count on the planner's stale supplier snapshot; now uses the terms of record, and `edi report` enforces an invariant against it (protocol amendment 2).
- 2026-11-26: A dev forecast run could replace research forecast metrics. Artifacts now record the producing config, reports refuse to mix configs, and dev and CI configs use separate directories.
- 2026-11-26: Mobile horizontal overflow on several pages; clipped table columns; journey tests on mobile.
