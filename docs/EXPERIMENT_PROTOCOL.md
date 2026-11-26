# Experiment protocol

Version 1.0. Frozen on 2026-11-25 before any benchmark result was inspected. Changes after freezing must be appended in section 9 with a reason, and results produced under an earlier version must say so.

## 1. Hypotheses

- **H1 (accuracy vs decisions).** Ranking forecasting approaches by accuracy (pinball loss, WAPE) does not reliably match ranking them by downstream decision cost. Test: compare rankings of forecast variants on both criteria (Kendall tau), and the per-series correlation between forecast-error improvement and decision-cost improvement.
- **H2 (validation under unreliable data).** Wrapping a policy with the validation layer lowers the unsafe-decision rate and total cost including governance costs, relative to the same policy unwrapped, under the unreliable-data condition.
- **H3 (overhead under normal operations).** Under normal conditions the validation layer's net cost change is within plus or minus 2% of total cost. A larger increase is reported as overhead.
- **H4 (risk-aware optimization).** The mean-CVaR policy lowers CVaR90 of per-series cost relative to the expected-cost policy at an expected-cost increase below 5%.
- **H5 (censored demand).** On artificially censored in-stock days, hourly-profile recovery reduces absolute daily demand error and bias relative to treating observed sales as demand.

These are hypotheses to test. Rejections are reported.

## 2. Data windows (days are 1-based within the 90-day train split; 91 to 97 is the official eval split)

| Purpose | Days |
|---|---|
| Feature warm-up | 1 to 28 |
| Stage A forecast fit | targets 29 to 69 |
| Stage A conformal calibration | targets 70 to 76 |
| Tuning decisions (policy parameters, validator thresholds) | decision days 77 to 90 |
| Stage B forecast fit (refit, same hyperparameters) | targets 29 to 83 |
| Stage B conformal calibration | targets 84 to 90 |
| **Final test decisions** | **decision days 91 to 97** |

Hourly profiles for recovery use only days inside the corresponding fit window. Nothing from days 91 to 97 is used for any choice.

## 3. Conditions

- **Normal:** demand follows the reference path, no faults, no disruptions.
- **Unreliable data:** one or more of: inventory record error (phantom stock, recorded = true x (1 + U(0.5, 2.0)), affecting 30% of series for 2 to 4 consecutive days), stale supplier snapshot (the policy sees pre-change capacity, eligibility or cost), stale sales history (last 2 days missing), forecast distribution shift (demand x 1.35 from a random day). Faults are drawn per series and realization.
- **Disruptions:** supplier failure, lead-time increase (primary lead 1 to 2), capacity reduction (primary capacity x 0.4), procurement cost increase (+25%), transportation disruption (expedite unavailable), budget reduction (x 0.5), demand spike (x 1.6, 2 days), demand collapse (x 0.5, 3 days), and a combined case.
  - Tuning set: demand spike, capacity reduction, cost increase.
  - **Held-out set** (never used for tuning): supplier failure, lead-time increase, transportation disruption, budget reduction, demand collapse, combined.

Reference demand is the observed daily demand for in-stock days and the recovered estimate for stockout days (real data) or the known latent demand (synthetic fixture). Sensitivity runs replace recovered estimates by observed sales (lower bound) and by recovery x 1.25 (upper bound).

## 4. Policies and ablations

P1 base-stock (safety factor z tuned on the tuning window), P2 point forecast + deterministic MILP, P3 calibrated quantiles + SAA MILP (K = 100 scenarios), P4 mean-CVaR SAA (alpha = 0.9, lambda tuned from {0.25, 0.5}), P5a = validation(P3), P5b = validation(P4). Oracle: retrospective bound only.

Ablations (wrapping P3 unless noted): without stockout-aware forecasting (quantiles trained on observed sales), without validation (= P3), without value of information (investigations replaced by escalation), without escalation (escalate outcomes execute the repaired action without review cost or reviewer), without risk-aware review (reviewer uses expected cost).

## 5. Metrics

Primary: **total cost per series-day**, including governance costs (investigation 0.6 x unit price, review 1.2 x unit price per event; sensitivity x0.5, x2, x4).

Secondary: expected cost, CVaR90 of per-series total cost over the test window, decision regret versus the oracle, hard-constraint violations under true conditions, fill rate, stockout-day frequency, waste rate (wasted / received), average working capital (inventory at cost), unsafe-decision rate, detection recall, unnecessary-intervention rate, automatic-decision coverage, investigation and escalation counts and costs, runtime, reproducibility (identical outputs on re-run with the same seed).

**Unsafe decision (defined before evaluation).** A candidate decision is unsafe if (a) it violates a hard constraint under true current conditions (eligibility, capacity, MOQ, budget), or (b) its ex-ante expected cost, evaluated with the true current state and authoritative constraints under the candidate's own forecast distribution, exceeds that of the best feasible action on the evaluation grid by more than half a day of expected revenue for the series. This separates decisions made on wrong inputs from bad luck.

**Unnecessary intervention.** Any non-recommend outcome on a candidate that is not unsafe.

## 6. Statistical treatment

- Common random numbers: demand path, faults and disruption timing depend only on (series, condition, realization); every policy sees the same draws. Policy-internal sampling uses separate seeded streams.
- Realizations: dev config 2, research config 3 per condition.
- Uncertainty: cluster bootstrap over series (1,000 resamples, seed 20261125) for means and paired differences; 95% percentile intervals. No p-values are reported as significance claims; intervals that exclude zero are described as such.

## 7. Forecast evaluation

Metrics: MAE, WAPE (sum |e| / sum y, undefined when sum y = 0 and then reported as null), bias (sum e / sum y), pinball loss averaged over quantiles {0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95}, 80% and 90% interval coverage and width, calibration curve. Evaluated against observed sales on all days, against observed sales on in-stock days only, and (synthetic only) against true latent demand. Segments: stockout vs in-stock days, category.

## 8. Reproduction

`edi run-all --config configs/research.yaml` with dataset revision recorded in `data/raw/freshretailnet/PROVENANCE.json`. Each run writes `artifacts/runs/<run_id>/manifest.json` with config hash, code version (git SHA), data hash, seeds and timings.

## 9. Amendments

**Amendment 1 (2026-11-25, after the first development run on the synthetic fixture, before any final run).**
The first development run was used for debugging and is not reported as a result. Changes:

1. *Approval rule artifact.* At the last day of the test window only same-day expedite can arrive, so every policy's final order tripped the expedite-share approval rule. The rule now applies only when a standard supplier is usable. It applies identically to all policies (the harness charges the review cost to every policy) and to the validator's G7 gate.
2. *Validator threshold tuning.* Section 2 lists validator thresholds as tuned on the tuning window, but the first run used config defaults. The soft-tolerance scale for G4 and G5 is now chosen from {1, 2, 4, off} on days 77 to 90 (normal, unreliable and tuning-set disruptions), together with the base-stock safety factor and the CVaR weight, which now use the same three-condition objective. An untuned variant (`P5a_untuned`) is reported as an ablation.
3. *Audit realism.* In the external-recommendation audit, the phantom-record fault now re-plans the action on the phantom record (as an upstream system that trusted the record would) instead of keeping the original action.
4. *Validator internals changed during engineering, before any reported run:* G3 separates claim reconciliation (standard-error tolerance) from the cost impact of stale terms; investigation is triggered by the value of verification relative to the candidate (EVPI is also reported). See ADR-0009.

Hypotheses, metrics, windows, conditions and the unsafe-decision definition are unchanged.

**Amendment 2 (2026-11-26, after the first research run, before results were published).**
Inspecting the decisions that P5a and P5b executed under unreliable data showed hard-constraint breaches after an `investigate` outcome. Cause: a harness bug, not a validator or policy rule. After the simulated stock count, the harness re-planned with true inventory but kept the planner's (possibly stale) supplier snapshot, while every other re-plan path (reject, escalation review) used the terms of record. Changes:

1. The investigation re-plan uses the terms of record, like the other re-plan paths.
2. `edi report` now checks a harness invariant: no order re-planned after a reject, review or stock count may breach a hard constraint. It refuses to produce a report otherwise. On the first research run it flagged 46 such decisions across all experiments (3 in P5a and 4 in P5b in the main unreliable-data comparison), all from this bug.
3. Forecast metrics, secondary-domain results and benchmark summaries now record the config that produced them, and reports refuse to mix configs. Dev and CI configs write to their own data and artifact directories. (A development forecast run had replaced the research forecast metrics; the research forecasts were regenerated bit-identically before the rerun.)

The first research run (`research-34e2e906a51d916f`) is superseded and not reported, except that `docs/BENCHMARK_FINDINGS.md` notes how its headline numbers differ. Policies, tuning grids, windows, conditions, metrics, hypotheses and the unsafe-decision definition are unchanged.

**Amendment 3 (2026-11-26, before the first run on FreshRetailNet-50K).** The real-data pilot uses a separate configuration and outputs. It samples 60 store-product pairs with equal allocation to historical stockout-frequency terciles, fits the common volume scale on days 1–69, uses two matched realizations per condition and 40 optimization paths, and fits at most 120 boosting rounds per model. The sample is a stratified pilot rather than a population estimate. The official split dates must agree with the protocol. Published promotion fields lack availability timestamps, so the pilot excludes target-day discount and activity from all models. Calendar and trailing weather features remain eligible. Score only target dates inside the named forecast evaluation window, while retaining earlier-origin predictions for stale-history simulation. Synthetic amendment 2 artifacts remain available as historical evidence.

The audit corrected the settlement model before inspecting real-data benchmark outputs. Log the submitted action and each hard breach even when a fulfillment system clips or refuses a line. Fulfill within current eligibility, availability, capacity, minimum quantities and budget. Apply budget in primary, alternate, then expedite order, with refused sub-minimum lines leaving their allocation available. Draw validator and reviewer randomness from matched, policy-independent streams within each world. These engineering changes apply to new runs. Comparisons with historical synthetic results are descriptive and include differences in configuration and settlement rules.

**Amendment 4 (2026-11-26, before selective replay).** Reprice breached P3 and P5a submissions at assumed incremental costs of 0, 5, 10, 25 and 50 USD per decision with at least one hard breach. Scenario amounts represent penalties, administrative rework, incremental sourcing overhead and other disruption net of modeled costs. This is a fixed-action sensitivity, with no feedback into the policy. Compare full and selective validation in fresh matched synthetic fault/disruption realizations over the same real demand input, using seed 20261125 + 1000003. Fix the selective route in advance: suppress discretionary G4/G5 escalations and require estimated verification value to exceed twice the count cost. Keep financial reconciliation, hard constraint checks, staleness, missing evidence and mandatory approvals. Compare unsafe decision counts, breached submissions, recommendation coverage, governance cost and paired total cost. The experiment adds independent worlds on the same evaluation dates and series, so it supplies no new retail holdout. Retain the protocol's series-clustered intervals and report a crossed store/product bootstrap as sensitivity, conditional on the observed evaluation week.
