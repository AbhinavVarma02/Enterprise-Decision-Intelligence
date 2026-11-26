# Competitive analysis

Sources were read on 2026-11-25. Commercial platforms are described only through their public pages, which are high level. Absence of a feature on a marketing page is not evidence that the product lacks it, so the table marks those cells "not stated".

## Feature comparison

| Capability | SAP IBP | Kinaxis Maestro | Aera Technology | Oracle SCM | Stockpyl | FRN-50K pipeline (Azar 2026) | This project |
|---|---|---|---|---|---|---|---|
| What-if scenario comparison | Yes (feature pages) | Scenarios within Solver Studio; platform page mentions simulation | Not stated | Not researched | Simulation | No | Yes, bounded in browser |
| Constrained supply optimization | Yes (heuristic, prioritization or optimization) | Yes, Gurobi-powered Advanced Solver Studio | Not stated | Not researched | Single-node and multi-echelon models | Newsvendor family | MILP with HiGHS, brute-force verified |
| Inventory optimization under variability | Yes, multi-echelon | Not stated on pages read | Not stated | Not researched | Yes | Quantile newsvendor | Scenario-based expected cost and CVaR |
| Probabilistic forecasting | Statistical and ML forecasting | Predictive AI | Not stated | Not researched | No | LightGBM ensemble | Calibrated quantiles, stockout-aware |
| Censored (stockout) demand handling | Not stated | Not stated | Not stated | Not researched | No | Yes (heuristic, Tobit) | Yes (hourly-profile recovery), controlled recovery test |
| Policy-based decision checks before action | Not stated | Governance mentioned | Yes: Policy Studio rules checked before a decision takes effect; non-compliant decisions go to a person | Not researched | No | No | Yes: seven explicit gates |
| Decision record and outcome capture | Performance monitoring vs plan | Learning from outcomes | Yes: Decision Ledger with context, policies evaluated, outcome | Not researched | No | No | Browser-local audit log, replay, JSON export |
| Tail-risk (CVaR) objective or gate | Not stated | Not stated | Not stated | Not researched | No | No | Yes |
| Value of information before committing | Not stated | Not stated | Not stated | Not researched | No | No | Yes, exact over a bounded action set |
| Cost of inaction and deferral | Not stated | Not stated | Not stated | Not researched | No | No | Yes |
| Public, reproducible benchmark of decision policies | No | No | No | No | Library, not a benchmark | Reproducible pipeline | Yes (the main deliverable) |
| Open source | No | No | No | No | Yes (MIT) | Code availability not checked | Yes |

## What is genuinely different here

The defensible claim is narrow:

> An open, reproducible benchmark that scores **decisions**, not forecasts, across normal, unreliable-data and held-out disruption conditions, and that measures what an independent validation layer adds on top of like-for-like policies, including the cost of the escalations it triggers.

Individual techniques (CVaR, conformal quantiles, newsvendor policies, value of information, policy rule checks) are established. Aera publicly describes policy checks and a decision ledger; SAP and Kinaxis describe scenario planning and optimization at scale. We do not claim novelty for any of these. The contribution is the combination in an open benchmark with fault injection, matched scenarios, coverage versus unsafe-decision trade-offs and honest negative results.

## Limitations relative to commercial platforms

- Single echelon, single SKU-location decisions. No multi-echelon network, no bill of materials, no production scheduling.
- Simulated suppliers, costs and disruptions. Real procurement data was not available.
- Browser-local governance only. No identity, roles, central audit store or integration with ERP systems beyond a mock adapter.
- No concurrency, no streaming data, no planner collaboration features.
- Scale: the research config evaluates hundreds of series on a laptop, not millions of planning objects.

## Sources

- SAP IBP features: https://www.sap.com/products/scm/integrated-business-planning/features.html and https://www.sap.com/products/scm/integrated-business-planning/features/inventory-optimization.html (the scenario-planning URL in the brief failed to load)
- Kinaxis: https://www.kinaxis.com/en/solutions/platform and https://www.kinaxis.com/en/maestro-solver-studio
- Aera: https://www.aeratechnology.com/technology/decision-governance/
- Stockpyl: https://stockpyl.readthedocs.io/en/latest/ and https://github.com/LarrySnyder/stockpyl (MIT License)
- Azar (2026): https://www.mdpi.com/2411-5134/11/5/89
- Oracle SCM was not researched in this session.
