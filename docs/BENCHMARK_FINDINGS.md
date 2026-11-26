# Benchmark findings

**Read this first.** Every result below comes from a synthetic fixture with the exact schema of FreshRetailNet-50K, not from the real dataset, which could not be downloaded in the build environment. Suppliers, costs, faults and disruptions are simulated, and the economics are assumptions (`configs/base.yaml`). The results show how the policies and the validator behave inside this simulator. They are not evidence about real stores, and no dollar figure here is a real cost or saving.

The protocol (`docs/EXPERIMENT_PROTOCOL.md`) was frozen before the first run. Two amendments are recorded there: the first after a debugging run, the second after the first research run exposed a harness bug. The numbers below come from the run after amendment 2.

## Summary

- **The validator made decisions safer but not cheaper.** Under unreliable data it stopped every unsafe proposal from P3 (174 of 4,200, all caused by a stale supplier snapshot), cut executed hard-constraint breaches from 177 to 0 and unsafe executed orders from 4.21% to 0.02% (one deferral). Total cost still rose by 0.67% (95% interval 0.33% to 0.99%). Before review and stock-count costs, P5a and P3 cost the same (about $67.30 a store-product day each); the whole increase is the $0.47 a day the validator spends on reviews and counts.
- **That cost comparison understates what a breach costs.** In the simulator a breached order is simply cut to what the supplier can deliver, so a breach costs only the resulting shortage. Rejected purchase orders, emergency sourcing and supplier penalties are not priced. A real deployment would have to put a number on those before the trade-off could be judged.
- **In normal operations and held-out disruptions validation changed cost by less than 0.1%** (normal: 0.01% lower, interval 0.03% lower to no change; disruptions: 0.05% higher, interval 0.01% to 0.09%). It escalated or rejected 0.4% and 2.8% of decisions.
- **The risk-aware optimizer (P4) was the cheapest real policy in every condition**, and lowered tail cost too: 1.3% cheaper than P3 in normal operations and 3.5% cheaper under unreliable data, with CVaR90 about 4% lower in both. In held-out disruptions P3 and P4 tied on mean cost, and P4's tail was 2% lower.
- **Stockout-aware forecasting mattered more than the validator.** Training on recovered demand instead of observed sales lowered P3's cost by 1.3% in normal operations, although the observed-sales model scored better on the usual accuracy metric.
- **A tuned base-stock rule was as good as the expected-cost MILP** in normal operations and with unreliable data (intervals include zero). The MILP only won during disruptions (1.3% cheaper).
- **The validator's soft risk gates added nothing measurable here.** Every unsafe proposal was caught by hard rules. Tuning set the soft thresholds so loose they were effectively off, and the untuned defaults raised cost by 0.3% to 1.4%.
- **In the second domain (cloud capacity), validation did lower cost** under unreliable data (2.1%) and disruptions (1.3%), with no clear effect in normal operations.

## What the benchmark measures

Each day, for each of 200 store-products, a policy proposes orders from three sources (primary supplier, pricier alternate, same-day expedite) under capacity, minimum-order and budget constraints. The simulator then plays out true demand, first-in-first-out spoilage and the true supplier terms. Seven policies face identical worlds:

| Policy | What it does |
|---|---|
| P1 | Base-stock rule on the median forecast, safety factor tuned on days 77 to 90 |
| P2 | Mixed-integer program on a point forecast (deterministic) |
| P3 | Mixed-integer program on 100 scenarios from calibrated, stockout-aware quantile forecasts, minimizing expected cost |
| P4 | Same as P3, minimizing a mix of expected cost and CVaR90 (weight tuned) |
| P5a | P3's proposal checked by the independent validator, which may recommend, investigate (stock count), defer, escalate (planner review) or reject (re-plan on the terms of record) |
| P5b | The validator over P4 |
| Oracle | Knows realized demand; a hindsight bound, not a policy |

Three conditions: **normal operations**; **unreliable data**, where 30% of decision days carry a fault (phantom stock in the record, a stale supplier snapshot, sales history two days late, or a forecast level shift); and **held-out disruptions** (supplier outages, lead-time increases, budget cuts, demand surges and collapses) of kinds and timings not used for tuning. Three demand realizations per condition. Days 91 to 97 are the official test split and were used once.

Costs per store-product day include procurement, holding, waste, lost sales at full price plus goodwill, and every stock count and planner review the validator triggers. A decision is **unsafe** if it breaks a hard constraint under the true terms, or if, given the true state, its expected cost exceeds the best order on the evaluation grid by more than half a day of revenue. The definition was fixed before evaluation.

## Hypotheses and verdicts

The verdict rules were fixed in the protocol.

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | Better forecast accuracy does not necessarily produce lower decision cost | Supported | The most accurate model against observed sales (LightGBM quantiles on observed sales, pinball 1.297) gave higher decision cost than the stockout-aware model (pinball 1.365): +$0.71 a day, interval +$0.51 to +$0.92. Rank correlation between accuracy and cost: 0.33 against observed sales, 0.60 against true demand. Measured against true demand, which only a synthetic fixture has, the stockout-aware model is also the most accurate (1.468). |
| H2 | Under unreliable data, validation lowers unsafe decisions **and** total cost including governance | Partially supported | Unsafe executed orders fell from 4.21% to 0.02% and breaches from 177 to 0, but total cost rose 0.67% (0.33% to 0.99%). |
| H3 | Under normal operations the validation layer's net cost change is within ±2% | Supported | −0.01% (−0.03% to 0.00%). |
| H4 | Mean-CVaR optimization lowers CVaR90 at an expected-cost increase below 5% | Supported | CVaR90 lower in all three conditions (normal $170 vs $177, unreliable $206 vs $215, disruptions $190 vs $194), and expected cost was lower or equal, not higher. |
| H5 | Hourly-profile recovery reduces error and bias on artificially censored days | Supported | On 2,944 in-stock days censored at a random afternoon hour, treating sales as demand had a bias of −50.9% and mean absolute error 10.3 units; recovery had +0.3% and 3.96. |

## What did not work, or worked less than hoped

- **Validation did not pay for itself in the retail domain.** The protocol's main hypothesis (H2) needed both fewer unsafe decisions and lower total cost. Only the first held.
- **Most interventions under unreliable data were unnecessary.** 24% of safe proposals were flagged. Of the 970 flagged safe decisions, 734 had sales history that arrived late. The freshness gate fails on missing history whether or not those days change the order, and the decision is then deferred or escalated (335 of each for P5a). A rule that asks how much the missing days could move the order is the obvious next step.
- **Escalation cost more than it saved.** Removing escalation (executing the validator's own hedge or the proposal instead) lowered P5a's cost under unreliable data by $0.37 a day (0.18 to 0.55).
- **Value of information did not move cost.** Replacing stock counts with escalations changed cost by −$0.04 a day (−0.17 to +0.10). Phantom-stock faults were common, but at the injected sizes they rarely made a proposal unsafe, so verifying them bought little.
- **Validation on top of the risk-aware policy was worse.** P5b cost 1.66% more than P4 under unreliable data, and even before review and count costs it was $0.71 a day more expensive. The cause has not been isolated.
- **The expected-cost MILP did not beat a tuned base-stock rule** outside disruptions.
- **The external-recommendation audit flagged 70% of safe proposals** that carried an injected fault. For integrity faults such as a stale supplier snapshot or a missing forecast, flagging is the intended behavior even when the specific order happened to be safe, but the rate shows the validator is conservative. It flagged 11% of unmodified proposals.
- **All forecasts under-predict true demand** (bias −2% to −7% on the test week), the stockout-aware one least.

## How the first research run differed

The first research run (`research-34e2e906a51d916f`) had the investigation re-plan bug described in amendment 2. Fixing it changed only the validated policies under unreliable data: executed hard breaches went from 3 (P5a) and 4 (P5b) to 0, and unsafe executed orders from 0.10% and 0.12% to 0.02%. Every cost figure in this document moved by $0.01 a day or less, and no verdict changed.

## Threats to validity

- **Synthetic data.** The fixture's demand, promotions and stock-outs come from a generator written for this project. Its known true demand makes leakage and recovery checks exact, but a model that fits the generator may fit real stores worse. Every hypothesis should be re-tested on FreshRetailNet-50K.
- **The simulator decides what "unsafe" means in practice.** Faults are injected by the same codebase that evaluates the validator, so the validator's catch rate partly reflects how faults were designed. The external-recommendation audit and the protocol's fixed unsafe definition limit this, but do not remove it.
- **Modeled reviewers.** Escalations are resolved by a simulated planner who verifies stock, re-plans with a risk-aware objective and errs 10% of the time. Real reviewers differ, and review cost is an assumption; the sensitivity table shows results move with it.
- **Short test window.** Seven days, three realizations. Intervals are cluster-bootstrap intervals over store-products and do not capture uncertainty in the simulator's assumptions.
- **One echelon, one item at a time.** No shared capacity across items, no multi-echelon effects.

## Reproduce

```bash
edi run-all --config configs/research.yaml   # about 105 minutes on 2 CPU cores
python scripts/findings_tables.py --write    # regenerates the tables below
python scripts/findings_digest.py            # every headline number, as plain text
```

## Result tables

<!-- GENERATED: scripts/findings_tables.py (do not edit by hand) -->

Run `research-76b4b4db2c95d63e` (code `2558d98`), data source `synthetic_fixture`, 200 store-products, 3 realizations per condition, test days 91 to 97, 298,200 simulated decisions in 104 minutes on 2 CPU cores. Tuned on days 77 to 90: base-stock z = 1.0, CVaR weight = 0.25, validator soft-threshold scale = 4.0. Harness invariant: 13,179 re-planned orders checked, 0 hard breaches.

### Policy results by condition

Cost per store-product day includes procurement, holding, waste, lost sales with goodwill, and review and stock-count costs (every policy pays for an approval review when an order's spend exceeds the approval threshold; the validator adds its own counts and reviews). Brackets: 95% cluster-bootstrap interval over store-products. Tail: average of the worst 10% of store-product daily costs. Unsafe: share of executed orders that were unsafe by the protocol's definition.

**Normal operations**

| Policy | Cost per day | Tail (CVaR90) | Fill rate | Waste | Review and count cost per day | Unsafe executed | Hard breaches |
|---|---|---|---|---|---|---|---|
| P1 base-stock rule | $57.04 ($50.91 to $64.08) | $173.86 | 96.5% | 2.1% | $0.38 | 0.17% | 0 |
| P2 point forecast + MILP | $59.68 ($53.04 to $67.01) | $185.07 | 88.8% | 0.1% | $0.02 | 0.00% | 0 |
| P3 quantiles + expected-cost MILP | $56.61 ($50.21 to $63.73) | $177.28 | 94.2% | 0.3% | $0.02 | 0.00% | 0 |
| P4 quantiles + mean-CVaR MILP | $55.88 ($49.84 to $62.80) | $170.45 | 97.9% | 1.4% | $0.07 | 0.00% | 0 |
| P5a validator over P3 | $56.60 ($50.21 to $63.73) | $177.24 | 94.2% | 0.3% | $0.02 | 0.00% | 0 |
| P5b validator over P4 | $55.90 ($49.86 to $62.82) | $170.45 | 97.9% | 1.4% | $0.07 | 0.00% | 0 |
| Oracle (hindsight bound) | $50.42 ($44.76 to $56.86) | $155.99 | 99.7% | 0.0% | $0.10 | n/a | 0 |

**Unreliable data**

| Policy | Cost per day | Tail (CVaR90) | Fill rate | Waste | Review and count cost per day | Unsafe executed | Hard breaches |
|---|---|---|---|---|---|---|---|
| P1 base-stock rule | $66.81 ($59.13 to $75.52) | $207.48 | 91.6% | 1.5% | $0.50 | 4.83% | 185 |
| P2 point forecast + MILP | $71.23 ($62.96 to $80.59) | $224.62 | 81.0% | 0.1% | $0.03 | 4.19% | 169 |
| P3 quantiles + expected-cost MILP | $67.36 ($59.24 to $76.50) | $215.33 | 87.8% | 0.2% | $0.04 | 4.21% | 177 |
| P4 quantiles + mean-CVaR MILP | $65.03 ($57.19 to $73.75) | $205.66 | 93.7% | 0.8% | $0.12 | 4.52% | 190 |
| P5a validator over P3 | $67.81 ($59.65 to $76.89) | $215.39 | 88.5% | 0.4% | $0.51 | 0.02% | 0 |
| P5b validator over P4 | $66.11 ($58.18 to $74.83) | $209.13 | 92.8% | 0.7% | $0.49 | 0.02% | 0 |
| Oracle (hindsight bound) | $58.14 ($51.37 to $65.80) | $182.29 | 99.5% | 0.0% | $0.29 | n/a | 0 |

**Held-out disruptions**

| Policy | Cost per day | Tail (CVaR90) | Fill rate | Waste | Review and count cost per day | Unsafe executed | Hard breaches |
|---|---|---|---|---|---|---|---|
| P1 base-stock rule | $61.22 ($54.61 to $69.18) | $192.99 | 92.1% | 3.3% | $0.35 | 0.88% | 0 |
| P2 point forecast + MILP | $62.49 ($55.45 to $70.61) | $199.30 | 85.7% | 0.8% | $0.09 | 0.00% | 0 |
| P3 quantiles + expected-cost MILP | $60.42 ($53.61 to $68.28) | $193.93 | 90.2% | 1.1% | $0.15 | 0.00% | 0 |
| P4 quantiles + mean-CVaR MILP | $60.40 ($53.69 to $67.99) | $189.86 | 93.4% | 2.3% | $0.28 | 0.00% | 0 |
| P5a validator over P3 | $60.45 ($53.64 to $68.29) | $193.93 | 90.2% | 1.1% | $0.16 | 0.00% | 0 |
| P5b validator over P4 | $60.44 ($53.72 to $68.04) | $189.89 | 93.5% | 2.4% | $0.28 | 0.00% | 0 |
| Oracle (hindsight bound) | $55.10 ($48.79 to $62.35) | $177.13 | 94.0% | 0.1% | $0.23 | n/a | 0 |

### Paired comparisons

Same store-products, same demand paths and faults. Difference in cost per store-product day (first minus second); negative means the first policy is cheaper.

| Comparison | Normal operations | Unreliable data | Held-out disruptions |
|---|---|---|---|
| P5a vs P3 (effect of validation) | −0.01 (−0.02 to +0.00) | +0.45 (+0.22 to +0.67) | +0.03 (+0.01 to +0.05) |
| P5b vs P4 (effect of validation) | +0.03 (+0.00 to +0.07) | +1.08 (+0.76 to +1.43) | +0.04 (+0.01 to +0.06) |
| P4 vs P3 (mean-CVaR vs expected cost) | −0.73 (−1.20 to −0.28) | −2.33 (−2.87 to −1.82) | −0.02 (−0.37 to +0.31) |
| P3 vs P2 (quantiles vs point forecast) | −3.07 (−3.49 to −2.66) | −3.88 (−4.30 to −3.46) | −2.07 (−2.37 to −1.76) |
| P3 vs P1 (MILP vs tuned base-stock) | −0.43 (−1.02 to +0.19) | +0.55 (−0.22 to +1.43) | −0.80 (−1.29 to −0.32) |
| P5b vs P3 | −0.70 (−1.16 to −0.25) | −1.25 (−1.80 to −0.75) | +0.02 (−0.34 to +0.35) |
| P3 vs oracle | +6.18 (+5.31 to +7.12) | +9.22 (+7.72 to +10.90) | +5.32 (+4.61 to +6.14) |

Relative differences for the validation comparisons:

| Comparison | Normal operations | Unreliable data | Held-out disruptions |
|---|---|---|---|
| P5a vs P3 | −0.01% (−0.03% to 0.00%) | +0.67% (+0.33% to +0.99%) | +0.05% (+0.01% to +0.09%) |
| P5b vs P4 | +0.05% (+0.01% to +0.13%) | +1.66% (+1.16% to +2.21%) | +0.06% (+0.02% to +0.11%) |

### Validator outcomes and detection

| Condition | Policy | Recommend | Investigate | Defer | Escalate | Reject | Unsafe candidates | Caught | Safe candidates flagged |
|---|---|---|---|---|---|---|---|---|---|
| Normal operations | P5a | 4182 | 0 | 0 | 18 | 0 | 0 | n/a | 0.4% of 4200 |
| Normal operations | P5b | 4134 | 0 | 0 | 60 | 6 | 0 | n/a | 1.6% of 4200 |
| Unreliable data | P5a | 3056 | 71 | 335 | 350 | 388 | 174 | 100% | 24.1% of 4026 |
| Unreliable data | P5b | 2998 | 48 | 391 | 343 | 420 | 190 | 100% | 25.2% of 4010 |
| Held-out disruptions | P5a | 4081 | 0 | 0 | 117 | 2 | 0 | n/a | 2.8% of 4200 |
| Held-out disruptions | P5b | 3982 | 0 | 0 | 213 | 5 | 0 | n/a | 5.2% of 4200 |

### Ablations

Difference in cost per store-product day against full P5a unless stated.

| Variant | Normal operations | Unreliable data | Held-out disruptions |
|---|---|---|---|
| P5a with P3 forecasting from observed sales (no stockout-aware target) | +0.71 (+0.50 to +0.92) | +1.14 (+0.90 to +1.39) | +0.39 (+0.25 to +0.56) |
| Validator without value of information (investigations become escalations) | +0.00 (+0.00 to +0.01) | −0.04 (−0.17 to +0.10) | −0.00 (−0.02 to +0.02) |
| Validator without escalation (escalations execute the validator's hedge or the candidate) | +0.01 (−0.00 to +0.02) | −0.37 (−0.55 to −0.18) | −0.03 (−0.05 to −0.01) |
| Reviewer re-plans for expected cost instead of mean-CVaR | +0.01 (−0.00 to +0.02) | +0.18 (+0.01 to +0.38) | −0.03 (−0.05 to −0.01) |
| Validator with default soft thresholds (not tuned) | +0.77 (+0.57 to +0.99) | +0.21 (+0.04 to +0.39) | +0.87 (+0.68 to +1.06) |
| P3 on observed-sales forecasts, vs P3 | +0.71 (+0.51 to +0.92) | +1.13 (+0.91 to +1.36) | +0.44 (+0.29 to +0.61) |
| P3 without validation, vs P5a | +0.01 (−0.00 to +0.02) | −0.45 (−0.67 to −0.22) | −0.03 (−0.05 to −0.01) |

### Forecast accuracy versus decision cost (P3, normal operations)

| Forecast | Decision cost per day | Pinball vs observed sales | WAPE vs observed | Bias vs observed | Pinball vs true demand |
|---|---|---|---|---|---|
| LightGBM quantiles, stockout-aware | $56.61 | 1.365 | 24.0% | +4.4% | 1.468 |
| Stockout-aware, no promotion inputs | $56.85 | 1.511 | 25.7% | +3.2% | 1.614 |
| LightGBM point | $57.23 | 1.324 | 23.5% | −0.6% | 1.507 |
| LightGBM quantiles, observed sales | $57.32 | 1.297 | 23.5% | −0.1% | 1.489 |
| Moving average (weekday-adjusted) | $57.92 | 1.704 | 29.8% | +1.6% | 1.845 |
| Seasonal naive | $58.25 | 2.058 | 35.6% | +1.6% | 2.160 |

### Sensitivity (unreliable data, P5a vs P3)

| Assumption changed | Relative cost change (95% interval) |
|---|---|
| goodwill x0.5 | +0.99% (+0.64% to +1.36%) |
| goodwill x2 | +0.45% (+0.05% to +0.81%) |
| holding x2 | +0.62% (+0.26% to +0.94%) |
| review x0.5 | +0.30% (−0.05% to +0.63%) |
| review x2 | +1.40% (+1.04% to +1.75%) |
| review x4 | +2.82% (+2.33% to +3.32%) |
| reviewer error 0 | +0.73% (+0.38% to +1.06%) |
| reviewer error 0.3 | +0.72% (+0.40% to +1.03%) |

### Bounds on unobserved demand (normal operations)

Reference demand on stockout days replaced by observed sales (lower) or recovery x 1.25 (upper).

| Policy | Lower bound | Upper bound |
|---|---|---|
| P1 base-stock rule | $53.09 | $63.55 |
| P2 point forecast + MILP | $54.38 | $67.35 |
| P3 quantiles + expected-cost MILP | $52.09 | $63.69 |
| P4 quantiles + mean-CVaR MILP | $52.35 | $61.77 |
| P5a validator over P3 | $52.09 | $63.68 |

### External-recommendation audit

240 benchmark candidates, each validated unchanged and with each injected fault (1,920 validations). 100% of unsafe candidates were flagged; 70% of safe candidates were flagged too.

| Injected fault | Unsafe | Flagged | Unsafe flagged |
|---|---|---|---|
| ineligible supplier | 100% | 100% | 100% |
| misreported cost | 0% | 53% | n/a |
| missing forecast | 0% | 100% | n/a |
| no order | 4% | 86% | 100% |
| phantom record | 0% | 81% | n/a |
| quantity x3 | 79% | 83% | 100% |
| stale snapshot | 0% | 100% | n/a |
| unchanged | 0% | 11% | n/a |

### Risk-coverage (validated decisions, all conditions)

| Soft-threshold scale | Automatic coverage | Coverage without approval routing | Unsafe among recommended |
|---|---|---|---|
| 0.25 | 14.7% | 15.2% | 0.00% |
| 0.5 | 35.9% | 37.0% | 0.00% |
| 1.0 | 81.7% | 83.0% | 0.00% |
| 2.0 | 90.0% | 91.2% | 0.00% |
| 4.0 | 90.3% | 91.5% | 0.00% |
| 8.0 | 90.4% | 91.6% | 0.00% |
| hard rules only | 90.4% | 91.6% | 0.00% |

### Second domain: cloud capacity (synthetic)

40 services, weeks 8 to 13. Cost per service-day.

| Policy | Normal operations | Unreliable data | Held-out disruptions |
|---|---|---|---|
| C1 reserve mean | $119.42 | $131.54 | $147.09 |
| C2 deterministic | $101.51 | $117.90 | $140.41 |
| C3 expected | $96.64 | $109.37 | $122.23 |
| C4 cvar | $96.56 | $108.04 | $119.57 |
| C5 validated | $96.98 | $107.08 | $120.70 |

| Paired | Normal operations | Unreliable data | Held-out disruptions |
|---|---|---|---|
| C5 vs C3 | +0.35% (−0.12% to +0.91%) | −2.09% (−4.06% to −0.16%) | −1.25% (−2.37% to −0.20%) |
| C4 vs C3 | −0.08% (−0.80% to +0.68%) | −1.21% (−2.36% to −0.08%) | −2.17% (−3.60% to −0.62%) |
| C3 vs C1 | −19.08% (−23.76% to −14.49%) | −16.86% (−20.48% to −13.09%) | −16.90% (−21.09% to −12.86%) |

### Forecast evaluation (final stage, days 91 to 97)

| Model | WAPE, in-stock days | Bias, in-stock days | Pinball, all days | 80% coverage | Pinball vs true demand | Bias vs true demand | 80% coverage vs true demand |
|---|---|---|---|---|---|---|---|
| Seasonal naive | 36.2% | +2.0% | 2.058 | 81.7% | 2.160 | −4.8% | 78.2% |
| Moving average (weekday-adjusted) | 30.7% | +2.5% | 1.704 | 81.2% | 1.845 | −4.8% | 77.4% |
| LightGBM point | 24.3% | +0.3% | 1.324 | 81.1% | 1.507 | −6.8% | 74.6% |
| LightGBM quantiles, observed sales | 24.6% | +1.0% | 1.297 | 80.8% | 1.489 | −6.4% | 73.9% |
| LightGBM quantiles, stockout-aware | 25.2% | +4.9% | 1.365 | 85.2% | 1.468 | −2.2% | 81.9% |
| Stockout-aware, no promotion inputs | 26.7% | +4.2% | 1.511 | 85.4% | 1.614 | −3.3% | 82.8% |

Controlled censoring experiment (in-stock days censored from a random hour in [12, 20]; truth is the observed full-day sales; 2,944 days):

| Estimate | Mean absolute error | Bias |
|---|---|---|
| Observed sales as demand | 10.31 | −50.9% |
| Hourly-profile recovery | 3.96 | +0.3% |

<!-- END GENERATED -->
