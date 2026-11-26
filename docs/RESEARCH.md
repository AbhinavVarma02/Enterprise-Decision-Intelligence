# Research log

Access date for every web source below: 2026-11-25 (America/New_York), unless noted. "Verified" means the bibliographic facts (title, authors, venue, year) were checked against the publisher, arXiv or an index such as RePEc/dblp during this session. Findings are paraphrased; see the source for exact wording.

## 1. Dataset

### FreshRetailNet-50K (primary)

- Dataset card: https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K (verified)
- Paper by Wang, Gu, Long, Li, Shen, Fu, Zhou and Jiang. *FreshRetailNet-50K: A Stockout-Annotated Censored Demand Dataset for Latent Demand Recovery and Forecasting in Fresh Retail.* First submitted 2025-05-22, revision 6 dated 2026-11-20, checked 2026-11-26. [arXiv record](https://arxiv.org/abs/2505.16319)
- Baseline code: https://github.com/Dingdong-Inc/frn-50k-baseline (README read through raw.githubusercontent.com).
- License: CC BY 4.0 (stated on the dataset card). Attribution and citation are required; see `THIRD_PARTY_NOTICES.md`.
- The audited Hub revision is `c374e85975c82816c495acfa904cc55ab14a47d3`. Both parquet file hashes and the full-partition counts are in `artifacts/real/dataset_audit.json`. [Pinned dataset](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/c374e85975c82816c495acfa904cc55ab14a47d3)

Schema (19 fields, from the card): `city_id`, `store_id`, `management_group_id`, `first_category_id`, `second_category_id`, `third_category_id`, `product_id` (int64 encoded IDs); `dt` (date string); `sale_amount` (float, daily sales, globally normalized and scaled by an undisclosed coefficient); `hours_sale` (24 floats); `stock_hour6_22_cnt` (int, out-of-stock hours between 06:00 and 22:00); `hours_stock_status` (24 ints); `discount` (1.0 means no discount); `holiday_flag`, `activity_flag` (ints); `precpt`, `avg_temperature`, `avg_humidity`, `avg_wind_level` (floats).

The downloaded files contain 4,500,000 training rows (March 28 to June 25, 2024) and 350,000 evaluation rows (June 26 to July 2, 2024). Both contain the same 50,000 store-product pairs across 898 stores, 18 cities and 865 distinct product IDs. The files total about 115 MB. At least one flagged business-hour stockout occurred on 44.27% of training rows and 40.98% of evaluation rows. These are daily rates.

The daily stockout count equals the number of `1` values in hours 06:00–21:59 on every downloaded row. Including hour 22 creates 2,020,515 disagreements. This verifies the half-open business-hour window and the out-of-stock flag convention for this revision.

Implications for this project:

1. `sale_amount` is normalized, so all currency figures are assumptions applied to normalized units. We never present them as real money.
2. Observed sales are censored whenever any hour is out of stock. Real latent demand during true stockouts is unobservable, so controlled recovery experiments use artificially censored in-stock days where the answer is known.
3. Weather fields are same-day actuals. A replenishment decision made the previous day could not have known them, so models use only lagged weather (ADR-0005).
4. The synthetic study evaluates a planned-promotion assumption and a no-promotion variant. The retail pilot excludes target-day discount and activity because availability timestamps are missing. It uses the holiday calendar and trailing weather.

The observed-data pilot used 60 deterministically stratified pairs. Selection and volume scales use days 1–69. The benchmark assumes new inventory, supplier, cost and disruption scenarios. [Independent audit](RELEASE_AUDIT.md)

Paired retail sensitivity resamples stores and products independently, following the crossed-row/column bootstrap, and retains all days and scenario realizations within each pair. [Owen, The Pigeonhole Bootstrap](https://arxiv.org/abs/0712.1111)

### Closely related prior work on the same dataset

- Azar, J. *A Reproducible, Leakage-Free Pipeline for Censored Demand Forecasting and Inventory Optimization on FreshRetailNet-50K.* Inventions 11(5):89, published 2026-08-30, DOI 10.3390/inventions11050089 (verified via https://www.mdpi.com/2411-5134/11/5/89).
  - Finding: latent demand via a fast heuristic and a Tobit baseline, a LightGBM ensemble on 117 leakage-checked features, and 20 newsvendor-family policies chosen on a validation fold under a fill-rate floor. Reports about 32.8% WAPE after calibration and notes that profit figures on censored evaluation data are proxies whose bias direction is not identified.
  - Relevance: this overlaps heavily with our forecasting and policy layer. Our project does **not** claim novelty for censored-demand forecasting or newsvendor policies on this dataset. Our contribution is elsewhere (validation, abstention, disruptions, risk, value of information; see `COMPETITIVE_ANALYSIS.md`). We adopt the same honesty about censored evaluation.

## 2. Enterprise context (publicly disclosed problems)

We document disclosed problems only. Nothing here implies these companies lack internal solutions.

| Company | Source | Disclosed problem relevant here |
|---|---|---|
| Target | Q1 2022 earnings release, 2022-05-18, https://corporate.target.com/press/release/2022/05/target-corporation-reports-first-quarter-earnings ; updated plan, 2022-06-07, https://corporate.target.com/press/releases/2022/06/Target-Corporation-Announces-Updated-2022-Plan-Foc | Operating margin of 5.3% well below expectations, attributed mainly to actions to reduce excess inventory plus freight costs; follow-up plan of markdowns, inventory removal and order cancellations. A clear case of demand shift turning inventory decisions into margin loss. |
| Micron Technology | FY2025 10-K and 10-Q risk factors, https://investors.micron.com/ (filing PDFs) | Significant average-selling-price volatility driven by supply and demand imbalance; stated difficulty in accurately forecasting customer and distributor demand and inventory levels. |
| Applied Materials | FY2025 10-K, https://www.sec.gov/Archives/edgar/data/6951/000162828025056742/amat-20251026.htm | Supply chain disruptions or failure to forecast demand can raise costs or create excess or obsolete inventory; some key parts come from a single or limited set of suppliers (earlier 10-Ks describe qualifying alternate suppliers as mitigation). |
| Tyson Foods | FY2022 to FY2025 10-Ks, e.g. https://www.sec.gov/Archives/edgar/data/100493/000010049322000097/tsn-20221001.htm | Earnings depend on volatile commodity and raw material costs and availability; livestock disease outbreaks and logistics disruptions affect supply and demand for perishable products. |
| Walmart | FY2026 10-K / annual report, https://stock.walmart.com/ | Forward-looking risk statements cite supply chain challenges, tariffs, inflation and recessionary pressure as factors affecting results. |

Not researched in depth this session: Intel, AMD, Amazon, PepsiCo. Their disclosures are not cited anywhere in the project.

Mapping to this project: demand shift and collapse scenarios (Target), single-source supplier failure and qualification of alternates (Applied Materials), perishable supply and cost shocks (Tyson), forecast-driven inventory imbalance (Micron). The benchmark simulates these mechanisms on retail data; it does not model these companies.

## 3. Inventory record inaccuracy

- DeHoratius, N. and Raman, A. (2008). *Inventory Record Inaccuracy: An Empirical Analysis.* Management Science 54(4):627-641. DOI 10.1287/mnsc.1070.0789 (verified, RePEc).
  - Finding: record inaccuracy is common in retail and varies with auditing practice, store complexity and distribution structure.
  - Relevance: motivates the "inventory record error" fault class and the cycle-count investigation action priced by value of information.
- DeHoratius, N., Mersereau, A. J. and Schrage, L. (2008). *Retail Inventory Management When Records Are Inaccurate.* M&SOM 10(2):257-277 (listed in the RePEc reference list; not opened).

## 4. Scientific methods

| Topic | Reference (verified) | How it is used |
|---|---|---|
| Predict-then-optimize | Elmachtoub, A. N. and Grigas, P. *Smart "Predict, then Optimize".* arXiv:1710.08005 (v5, 2020-11-19); later published in Management Science (2022) per our prior knowledge, not re-verified | Motivates evaluating forecasts by downstream decision cost (decision regret) rather than accuracy alone. We do not implement SPO+ training. |
| Decision-focused learning survey | Mandi, Kotary, Berden, Mulamba, Bucarey, Guns, Fioretto. JAIR 80:1623-1701 (2024). arXiv:2307.13565 | Background and terminology; justification for keeping a two-stage pipeline with decision-based evaluation given CPU limits. |
| CVaR optimization | Rockafellar, R. T. and Uryasev, S. *Optimization of Conditional Value-at-Risk.* Journal of Risk 2(1):21-42 (2000) | Linear-programming CVaR formulation in the risk-aware policy and CVaR metrics. |
| Conformal quantile calibration | Romano, Y., Patterson, E., Candès, E. J. *Conformalized Quantile Regression.* NeurIPS 2019, pp. 3543-3553. arXiv:1905.03222 | Split-conformal adjustment of predicted quantiles on a held-out calibration window. |
| Censored demand | Huh, W. T., Levi, R., Rusmevichientong, P., Orlin, J. B. *Adaptive Data-Driven Inventory Control with Censored Demand Based on Kaplan-Meier Estimator.* Operations Research 59(4):929-941 (2011). DOI 10.1287/opre.1100.0906 | Background on why sales-based estimates are biased; our recovery uses the dataset's hourly stock flags instead of Kaplan-Meier. |
| Perishable inventory | Nahmias, S. *Perishable Inventory Theory: A Review.* Operations Research 30(4):680-708 (1982). DOI 10.1287/opre.30.4.680 | Fixed-life FIFO inventory model in the simulator. |
| Selective decisions | Geifman, Y. and El-Yaniv, R. *Selective Classification for Deep Neural Networks.* NeurIPS 2017. arXiv:1705.08500 | Risk-coverage view: we report unsafe-decision rate against automatic-decision coverage. |
| Simulation library | Stockpyl 1.0, L. V. Snyder, MIT License (LICENSE file in https://github.com/LarrySnyder/stockpyl), docs https://stockpyl.readthedocs.io/en/latest/ | Comparator. Implements EOQ, newsvendor, base-stock, (s,S), multi-echelon optimization and simulation, and supply-uncertainty models. Not a dependency (ADR-0004). |

Expected value of information and value of perfect information follow the standard decision-analysis definitions (Raiffa and Schlaifer, *Applied Statistical Decision Theory*, 1961). This textbook reference was not re-verified online this session.

Common random numbers for matched policy comparison is standard simulation practice; our implementation and test are in `src/edi/benchmark/scenarios.py` and `tests/test_benchmark.py`.

## 5. Platform constraints (Cloudflare Pages, Free plan)

From https://developers.cloudflare.com/pages/platform/limits/ (verified 2026-11-25): 20,000 files per site, 25 MiB maximum single file, 500 builds per month, 1 concurrent build, 20-minute build timeout, 100 header rules in `_headers`, 2,100 redirects, 100 projects per account, and a limit on new projects during the first 48 hours of an account. Our build budget: under 3 MB total, no file over 1 MB, under 100 files (enforced by `apps/web/scripts/check-size.mjs`).

Pages Functions and Workers pricing pages were not needed because the site uses no server-side compute (ADR-0003).

## 6. Limitations of this research phase

- Enterprise research is a focused sample, not a survey. Several companies named in the brief were not researched.
- Competitor capabilities come from public marketing pages, which describe features at a high level and omit methods. SAP's scenario-planning page failed to load; SAP feature pages found through search were used instead.
- The author's earlier portfolio sites were not reachable from the build shell; they were reviewed through a browser screenshot where possible (see `docs/DESIGN_SYSTEM.md`).
