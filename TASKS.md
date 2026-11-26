# TASKS

Status values: todo, doing, done, blocked. Priority follows MASTER_PROMPT.md section 24.

| ID | Task | Depends on | Acceptance criteria | Status |
|---|---|---|---|---|
| T0 | Continuity files, repo init, environment inspection | none | Files exist; new agent can orient from repo alone | done |
| T1 | Focused research, competitive analysis, architecture review, ADRs, frozen protocol | T0 | RESEARCH.md, COMPETITIVE_ANALYSIS.md, ARCHITECTURE.md, ADR 0001-0008, EXPERIMENT_PROTOCOL.md v1.0 | done |
| T2 | Ingestion (real downloader + synthetic fixture), validation, quarantine, curated tables, provenance | T1 | `edi pipeline` deterministic, integrity tests pass | done |
| T3 | Forecasting: baselines, LightGBM point and quantile, stockout-aware target, conformal calibration, metrics, leakage tests | T2 | Metrics artifact, leakage test passes | done |
| T4 | Simulator, finance model, disruption and fault scenarios | T2 | Conservation and accounting property tests pass | done |
| T5 | Optimization policies P1-P4, oracle, brute-force checks, infeasibility handling | T3, T4 | Reference-problem tests pass | done |
| T6 | Validation engine (7 gates), VOI, cost of inaction, exception prioritization, decision schema | T5 | Known-invalid decisions detected in tests | done |
| T7 | Benchmark runner, conditions, ablations, sensitivity, bootstrap, fault-injection detection | T6 | Reproducible artifacts in artifacts/benchmark | done |
| T8 | Secondary domain: cloud capacity reservation | T6 | Reuse demonstrated; limitations documented | done |
| T9 | Export web artifacts and golden fixtures | T7, T8 | JSON under size budget; fixtures generated | done |
| T10 | Web app: design system, 7 pages, TS evaluator and gates, parity tests | T9 | Core journey works; vitest parity passes | done |
| T11 | Playwright e2e and screenshots, visual refinement pass | T10 | Screenshots at 3 viewports reviewed; issues fixed | done |
| T12 | Docs, README, security review, CI workflow, deployment commands | T11 | Docs match implementation; build verified | done |
| T13 | Real-data run on FreshRetailNet-50K | dataset access | Verified official revision and reproducible pilot artifacts alongside preserved synthetic outputs | done |
| T14 | Cloudflare Pages deployment | T12, credentials | Verified pages.dev URL | doing (dedicated project created) |
| T15 | Research rerun after harness fix (amendment 2), refresh findings, screenshots and docs | T7 | Invariant passes; docs match artifacts | done |
| T16 | Independent trade-off, inference and engineering audit | T13 | Paired safety and cost reconciliation, breach sensitivity, fresh selective replay, regression suites and documentation | done |
| T17 | GitHub publication and hosted Actions | authorization | Authorized publication and actual workflow run | blocked (publication authorization) |
