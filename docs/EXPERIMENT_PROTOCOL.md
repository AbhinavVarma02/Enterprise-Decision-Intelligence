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

None yet.
