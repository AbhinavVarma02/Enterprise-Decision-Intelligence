# Benchmark findings

**Read this first.** Every result below comes from a synthetic fixture with the exact schema of FreshRetailNet-50K, not from the real dataset, which could not be downloaded in the build environment. Suppliers, costs, faults and disruptions are simulated, and the economics are assumptions (`configs/base.yaml`). The results show how the policies and the validator behave inside this simulator. They are not evidence about real stores, and no dollar figure here is a real cost or saving.

The protocol (`docs/EXPERIMENT_PROTOCOL.md`) was frozen before the first run. Two amendments are recorded there: the first after a debugging run, the second after the first research run exposed a harness bug. The numbers below come from the run after amendment 2.

## Summary

{{SUMMARY}}

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

{{HYPOTHESES}}

## What did not work, or worked less than hoped

{{NEGATIVE}}

## How the first research run differed

{{SUPERSEDED}}

## Threats to validity

- **Synthetic data.** The fixture's demand, promotions and stock-outs come from a generator written for this project. Its known true demand makes leakage and recovery checks exact, but a model that fits the generator may fit real stores worse. Every hypothesis should be re-tested on FreshRetailNet-50K.
- **The simulator decides what "unsafe" means in practice.** Faults are injected by the same codebase that evaluates the validator, so the validator's catch rate partly reflects how faults were designed. The external-recommendation audit and the protocol's fixed unsafe definition limit this, but do not remove it.
- **Modeled reviewers.** Escalations are resolved by a simulated planner who verifies stock, re-plans with a risk-aware objective and errs 10% of the time. Real reviewers differ, and review cost is an assumption; the sensitivity table shows results move with it.
- **Short test window.** Seven days, three realizations. Intervals are cluster-bootstrap intervals over store-products and do not capture uncertainty in the simulator's assumptions.
- **One echelon, one item at a time.** No shared capacity across items, no multi-echelon effects.

## Reproduce

```bash
edi run-all --config configs/research.yaml   # about 95 minutes on 2 CPU cores
python scripts/findings_tables.py --write    # regenerates the tables below
python scripts/findings_digest.py            # every headline number, as plain text
```

## Result tables

<!-- GENERATED: scripts/findings_tables.py (do not edit by hand) -->
<!-- END GENERATED -->
