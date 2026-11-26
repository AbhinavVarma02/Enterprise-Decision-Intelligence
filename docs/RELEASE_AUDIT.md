# Independent release audit

Verified 2026-11-26. This audit preserves the controlled synthetic benchmark and adds a pilot driven by observed retail sales and stockout flags. Supplier terms, inventory positions, disruption events, review behavior and financial inputs are modeled in both studies.

## Dataset and temporal controls

The audited FreshRetailNet-50K revision is `c374e85975c82816c495acfa904cc55ab14a47d3`, published by Dingdong-Inc under CC BY 4.0. Both official Parquet file hashes were recalculated against download provenance. The two partitions contain the same 50,000 store-product pairs across 898 stores, 18 cities and 865 product IDs. The scan found zero duplicate `(store, product, date)` keys and zero malformed hourly arrays. [Pinned source](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/c374e85975c82816c495acfa904cc55ab14a47d3) · [Full data audit](../artifacts/real/dataset_audit.json)

| Partition | Dates | Observed rows | Rows with a business-hour stockout |
|---|---|---:|---:|
| Official train | 2024-03-28 through 2024-06-25 | 4,500,000 | 1,992,006 (44.27%) |
| Official eval | 2024-06-26 through 2024-07-02 | 350,000 | 143,438 (40.98%) |

The daily counter matches `1` flags in hours 06:00–21:59 on every row. The 60-series pilot uses equal allocation across historical stockout-frequency terciles, covering 57 stores and 53 products. It retained all 5,820 rows, of which about 43.7% had a business-hour stockout. Selection and the 35.43× volume scale use days 1–69. The scale is an assumption applied to publisher-normalized sales. The data loader uses column projection and filters series before materializing hourly arrays. It verifies the original partition boundaries and keeps their labels.

Stage A fits on targets 29–69, calibrates on 70–76 and supplies policy tuning on 77–90. Stage B fits on 29–83, calibrates on 84–90 and scores targets on 91–97. Different stages reuse historical observations for different roles, with separation within each stage. Forecast features use observed history through the origin, calendar information and lagged weather. Published discounts and activity are excluded from the pilot because advance availability is unknown. Rolling evaluation uses prior days of observed data as they become available. Forecast scoring excludes pre-window targets that only support the stale-history simulation.

For the observed-sales and stockout-aware quantile models, nominal 80% intervals covered 83.65% and 79.53% of the pooled official target rows, respectively. On in-stock target rows the rates were 85.97% and 79.13%. The metrics pool several origins and horizons per target, so they are aggregate calibration diagnostics. Stage B marked 503 of 2,542 recovered stockout rows low confidence. The controlled H5 test evaluates observed full-day sales after artificial censoring on 565 eligible days. [Forecast artifact](../artifacts/real/forecast/metrics.json)

## Safety, cost and uncertainty

Costs below are modeled USD per store-product day. The retail pilot uses 40 optimization paths, two matched world realizations per condition and 58,800 simulator decisions across its comparisons, ablations and sensitivities. Its main seven-policy comparison accounts for 17,640 decisions, with 840 per policy and condition. The legacy synthetic study used 100 paths, three realizations and 298,200 decisions across experiments, with 4,200 per main policy and condition. The configurations and modeled settlement differ, so these are independent within-study policy contrasts.

| Condition | Synthetic P3 → P5a | Retail pilot P3 → P5a | Pilot paired change (95% series-clustered interval) |
|---|---:|---:|---:|
| Normal operations | $56.61 → $56.60 | $134.92 → $140.24 | +3.94% (+1.73% to +6.89%) |
| Unreliable data | $67.36 → $67.81 | $160.93 → $159.01 | −1.19% (−2.58% to +0.77%) |
| Held-out disruptions | $60.42 → $60.45 | $145.76 → $148.55 | +1.91% (+0.13% to +4.42%) |

- **Proposals.** Synthetic P5a intercepted all 174 unsafe candidate proposals out of 4,200. Retail P5a intercepted all 45 out of 840. P5a generates proposals along its own inventory trajectory, which changes after verification, review, deferral or rejection.
- **Submissions and individual constraint flags.** Synthetic unwrapped P3 attempted 177 hard-breached submissions, with 177 distinct constraint flags in that run. Retail P3 attempted 46, comprising 32 primary capacity, 8 budget and 6 alternate qualification flags. Both P5a runs recorded zero breached submissions. A submission can trip multiple constraints, so aggregate flags and impacted policy-days are distinct metrics.
- **Decisions after routing.** Synthetic P3 had 177 unsafe decisions out of 4,200 (4.21%). P5a had one (0.02%), a deferral. Retail P3 had 47 out of 840 (5.60%), covering 46 hard breaches and one regret case. P5a had one (0.12%), also a no-order decision. Denominators include days without orders. These rates measure hard breaches or estimated ex-ante regret above half a day of revenue under the authoritative state.
- **Coverage.** P5a automatically recommended 3,056/4,200 synthetic proposals (72.76%) and 360/840 pilot proposals (42.86%) under unreliable data. It intervened on 970 and 435 proposals labeled safe by the frozen definition. Missing evidence or an approval requirement can still justify intervention. In the pilot's injected-candidate audit, recall was 100% and 69.82% of safe test cases were flagged across 1,920 evaluations of 240 sampled benchmark candidates.

The original bootstrap pairs policies on series and realization, averages all days in each episode, then averages realizations within series. Its 200 synthetic clusters are store-product pairs. It does not assume that 298,200 repeated decisions are independent. Shared stores, products and evaluation dates can still produce dependence across series. The pilot recomputes relative effects within each pair resample and adds a crossed store/product sensitivity across 57 stores and 53 products. Unreliable-data P5a versus P3 spans −3.47% to +1.78% under that sensitivity. Normal operations spans +0.24% to +9.29%. The pilot uses one evaluation week and two realizations, so neither interval captures week-to-week shifts or uncertainty in the simulator's assumptions. [Crossed bootstrap method](https://arxiv.org/abs/0712.1111) · [Pilot benchmark JSON](../artifacts/real/benchmark/summary.json)

## Incremental breach economics

The legacy simulation can settle orders after clipping some breaches. The audited pilot settles within the supplier availability, capacity, MOQ and budget constraints, while preserving the hard-breach flag on the submitted order. The existing cost model charges procurement, expediting, lost revenue, goodwill and governance. The sensitivity below prices additional consequences once per hard-breached submission. It excludes replacement product cost or expedites already charged and downtime or shortages already monetized in the simulator. All amounts are illustrative assumptions.

| Added cost per breach | Contract penalty | Administrative rework | Incremental sourcing | Other disruption | Synthetic P5a − P3 per day | Pilot P5a − P3 per day |
|---:|---:|---:|---:|---:|---:|---:|
| $0 | $0 | $0 | $0 | $0 | +$0.45 | −$1.92 |
| $5 | $0 | $5 | $0 | $0 | +$0.24 | −$2.20 |
| $10 | $0 | $5 | $3 | $2 | +$0.03 | −$2.47 |
| $25 | $5 | $5 | $10 | $5 | −$0.60 | −$3.29 |
| $50 | $10 | $10 | $20 | $10 | −$1.66 | −$4.66 |

In the synthetic run the total modeled cost delta was $1,884.91 over 4,200 matched policy-days. Dividing by 177 avoided breached submissions gives **$10.65 per breach**. In the pilot the point estimate already favors validation at zero additional charge. The zero-charge interval includes a cost increase and a cost decrease. These are fixed-action scenario repricings, so the policies do not change behavior at the threshold.

## Selective review and negative findings

The selective replay fixed its rule before evaluation and used a fresh seed for matched simulated faults and disruptions on the same series and dates. It retained hard checks, financial reconciliation, missing-evidence and freshness rules, and mandatory approvals. It suppressed discretionary risk escalations and raised the verification hurdle to twice the assumed count cost. [Selective replay artifact](../artifacts/real/benchmark/selective_validation.json)

| Condition | Governance per day, full → selective | Unsafe decisions, full → selective | Total cost change (95% series-clustered interval) |
|---|---:|---:|---:|
| Normal | $2.65 → $0.82 | 3 → 0 | −3.51% (−5.85% to −1.79%) |
| Unreliable | $2.59 → $1.17 | 4 → 3 | −0.68% (−2.42% to +0.65%) |
| Held-out disruptions | $2.09 → $0.82 | 1 → 0 | −1.39% (−3.19% to +0.07%) |

Both variants had zero hard-breached submissions in the replay. Under unreliable data, recommendation coverage rose from 40.95% to 64.88%. The observed replay supports reduced review overhead and preserved hard-constraint safety in these worlds. It supplies limited evidence about overall cost under unreliable data or disruption, and insufficient evidence about rare harms on unseen retailers or weeks.

- **Soft gates and escalation.** In the legacy synthetic run, all unsafe proposals were caught by hard rules, tuning selected a loose risk threshold, and removing escalation lowered cost by $0.37 per day under unreliable data. In the pilot, Stage A tuned to the default scale, yet 284 of 398 normal P5a escalations also tripped a soft risk gate. The reviewer changes both inventory evidence and the objective and charges for intervention. The no-escalation ablation therefore compares two whole routing behaviors. It lowers pilot unreliable-data cost by $1.24/day, with a series-clustered interval from −$2.21 to −$0.34.
- **Stock counts.** The synthetic no-VOI cost effect was −$0.04/day (−$0.17 to +$0.10). Replacing counts with reviews in the pilot increased cost by $0.47/day (−$0.04 to +$1.07). Only 25 full P5a pilot unreliable-data decisions triggered counts. The prior, injected phantom-stock size, short recovery window and cost assumptions limit inference. Both EVPI versus the best hedged action and value versus the actual proposal are computed over the same bounded grid and discrete prior.
- **Risk-aware wrapper.** Synthetic P5b added $1.08/day over P4 under unreliable data, including about $0.37 governance and $0.71 net operating cost. The intervention changes the closed-loop inventory and subsequent orders, so the operating difference cannot be attributed to individual reviews from the aggregate. In the pilot the cost difference reversed in point estimate (−0.41%, interval −1.36% to +0.65%). Normal pilot P5b still cost 1.05% more than P4.
- **Conventional reorder baseline.** The moving-average base-stock policy has a tuning-window safety factor, supplier fallback, an expedite rule and budget fitting. In the pilot both P3 versus P1 normal and unreliable intervals include zero. Complexity alone adds little to this conservative baseline under simple single-item operations.

## Hypotheses

| ID | Synthetic verdict | Retail pilot verdict | Pilot evidence |
|---|---|---|---|
| H1 · Forecast accuracy and downstream cost ordering differ | Supported | Partially supported | Observed-sales quantiles win pinball loss. Recovered quantiles have the lowest simulated decision cost. The $1.80/day gap has a 95% interval of −$0.39 to +$4.12. Across the 60 matched series, Kendall tau between the two models' forecast-error and cost differences was 0.13. |
| H2 · Validation improves safety and lowers cost under unreliable data | Partially supported | Partially supported | Hard-breached submissions fell from 46 to 0. The modeled cost change was −1.19%, with an interval spanning zero. |
| H3 · Normal validation overhead stays within ±2% | Supported | Unsupported | The pilot interval extends above +2% and the point estimate is +3.94%. |
| H4 · Mean-CVaR lowers the tail at less than 5% higher mean cost | Supported | Supported by descriptive protocol rule | Tail cost fell in all three conditions. Mean cost changed by +1.48%, −1.61% and +0.82%, respectively. Tail effects have no inferential interval in the frozen verdict rule. |
| H5 · Recovery improves error and bias on artificially censored days | Supported | Supported | On 565 artificial censoring cases, MAE fell from 9.20 to 6.47 scaled units and bias moved from −33.28% to +2.31%. |

The findings depend on the reference demand. In the pilot's normal condition, P5a minus P3 is +$10.34/day at observed sales and +$0.74/day with recovery increased 25% on stockout days, versus +$5.32/day at the main recovery estimate. Observed sales form a plausible lower reference during censoring. The uplift is an assumption and supplies no statistical upper limit on true demand.

## Engineering findings and second domain

- Verified the stock-count repair path uses both corrected inventory and authoritative supplier terms. The real report checked 9,788 post-intervention re-plans and found zero hard breaches. The independent selective replay checked 1,501 re-plans and found zero. The preserved historical synthetic report records 13,179 checks and zero.
- Fixed pre-fit volume scaling, partition identity, pre-window metric contamination, permissive budget/MOQ fulfillment and policy-specific reviewer randomness. Candidate and executed action diagnostics retain separate labels. The solver returned 54,600 optimal decisions plus 4,200 conventional rule decisions in the pilot. Tests compare the objective with the FIFO evaluator and check the known two-day shelf-life LP relaxation gap. The oracle uses realized demand in a rolling horizon and is a retrospective reference.
- Reconciled pilot demand, inventory and financial ledgers across the saved episodes. Maximum absolute residuals were below `3e-14` for demand, `4e-13` for inventory and `2e-12` for the financial identity. Opening stock plus receipts equals sales plus waste plus closing stock. Total cost plus profit equals revenue plus lost revenue.
- Tightened the feasible action grid, kept sales data freshness in scenario replay, and prevented approval of blocked order options. History records the selected alternative's own costs, validates imported quantile dimensions and now includes nested scenario assumptions in new hash-chain entries. Legacy logs remain readable. Hash checks detect accidental entry changes. A valid prefix can still verify.
- Cloud capacity shares the decision schema, gate engine, value of information, CVaR, bootstrap, paired comparison and detection metrics. Its optimization, demand generator and financial model are domain-specific. Reservations impose weekly commitment and quotas. Spot interruptions, burstable workloads, on-demand usage and SLA penalties differ from inventory replenishment. The preserved 40-service synthetic result shows validation effects of +0.35% (normal), −2.09% (unreliable) and −1.25% (disruption). The 40-path audit rerun gave +0.18%, −2.06% and −1.22%. Both normal intervals include zero. [Original cloud evidence](../artifacts/benchmark/secondary_cloud.json) · [Audit rerun](../artifacts/real/benchmark/secondary_cloud.json)

## Reproduction and publication

The [README](../README.md) contains the pinned dataset, environment, CLI and browser commands. Preserve the historical synthetic artifacts by running fresh synthetic experiments in an isolated checkout. The pilot exports a separate data file alongside the synthetic workspace cases.

| Release check | Observed result |
|---|---|
| Python and data pipelines | 65 tests passed on Python 3.13. Ruff lint and format checks and mypy passed. The CI-sized synthetic pipeline, secondary domain and isolated export completed locally. |
| App and parity | 42 Vitest tests passed, including Python golden fixture parity. ESLint and TypeScript passed. |
| Production browser | 16 journey tests passed across desktop and mobile. All 21 axe scans passed across desktop, tablet and mobile. The remaining Studio and workspace controls were exercised in Chrome at tablet width. |
| Visual review | All seven pages captured at 1440, 820 and 390 px. The captures passed the document overflow check. [Screenshots](screenshots) |
| Dependency and bundle review | Zero known vulnerabilities in the locked Python and shipped npm dependency queries. The bundle contains only static assets and uses self-hosted fonts. |
| Release integrity | All seven public routes and two case deep links returned HTTP 200 with the expected HTML and security headers. All eight served JSON files matched the build byte for byte. `research_evidence.json` SHA-256 is `7d635d8847dfbccf06ca3898f2a75377c2f4cda2297441e62c6df2ff79f48354`. |
| Replay | Both forecast tables (31,500 total rows), 58,800 decisions and 8,400 episode totals matched exactly across two pilot runs after omitting timings. The full amendment 2 synthetic run was audited from its committed aggregates. |

The pilot benchmark replay took **192 seconds** with ten workers, plus **5.0 seconds** for forecasting. The single-process validator measured **3.5 ms p50** and **4.6 ms p95** across 400 saved decisions at 40 paths. Nine production Studio edits took 6–57 ms in Chrome (median 35 ms); the measured combinations varied with the assumptions. The production build is **1.05 MB** across 30 static files including header configuration. Its main JavaScript chunk is approximately **84 kB gzip**.

The initial Cloudflare build used source commit `6638da5ce64f5567d5c7358a3a0c91ec52d55248`. The follow-up GitHub release review caught Python 3.10 typing conflicts and a race between consecutive Studio edits. After those fixes, all three hosted jobs passed on source commit `6bad18062584abd1b5b3f6d6ddadbcaac00daebc`. The versioned research inputs and benchmark artifacts stayed byte-for-byte identical. The recomputed retail report matched the committed report apart from its generation timestamp. [Public repository](https://github.com/AbhinavVarma02/Enterprise-Decision-Intelligence) · [Hosted CI run](https://github.com/AbhinavVarma02/Enterprise-Decision-Intelligence/actions/runs/45876351092)

The publishable Git history passed Gitleaks and path review. The review found no tracked raw datasets, local working notes or generated run folders. The largest historical blob was a 611,069-byte screenshot. The updated Pages deployment serves the 29 expected files byte for byte and passed 16 browser workflows and 21 accessibility scans. It uses the existing static Pages project, and the repository uses standard public GitHub-hosted runners. Incremental infrastructure cost remains **$0**. [Production workspace](https://enterprise-decision-intelligence.pages.dev/) · [Deployment snapshot](https://ac1e6bae.enterprise-decision-intelligence.pages.dev/)

## Resume bullets

- Audited and released a seven-gate decision validation system and benchmark that replayed 58,800 simulated replenishment decisions using observed FreshRetailNet-50K inputs, reducing hard-breached submissions from 46 to 0 under matched unreliable-data scenarios.
- Quantified the safety and cost trade-off with paired, clustered analysis. Identified a modeled $10.65 breach-cost threshold in the controlled synthetic benchmark and tested a selective review policy that cut governance cost from $2.59 to $1.17 per decision day in fresh unreliable-data scenarios.
