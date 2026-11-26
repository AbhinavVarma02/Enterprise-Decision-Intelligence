# Data model

Data moves through four layers. Each layer is a plain file on disk, so every intermediate result can be inspected with DuckDB, pandas or a text editor. Nothing here is a production data platform; it is the smallest structure that keeps raw data, cleaning decisions and derived numbers separate and traceable.

```
data/raw/<source>/        untouched input + PROVENANCE.json (hashes, revision, generator params)
data/staged/              typed, one row per series-day, quarantine applied
data/quarantine/          rejected rows with a reason code
data/curated/             dense panel, forecasts, recovered demand, data_quality.json
data/edi.duckdb           the same curated tables, queryable
artifacts/                benchmark, forecast and secondary-domain summaries (JSON)
apps/web/public/data/     small JSON exports for the static site
```

`data/` is gitignored. `data/manifest.json` records the run id, config hash, git SHA and SHA-256 of every file written by the last pipeline run.

## Raw

FreshRetailNet-50K columns, kept as delivered (the synthetic fixture writes the same 19 columns with the same types):

| Column | Type | Meaning |
|---|---|---|
| city_id, store_id, management_group_id, first/second/third_category_id, product_id | int | Identifiers and category hierarchy |
| dt | date string | Calendar day |
| sale_amount | float | Daily sales, normalized by the publisher (not units or currency) |
| hours_sale | list[float] x 24 | Hourly sales |
| stock_hour6_22_cnt | int | Hours out of stock between 06:00 and 22:00 |
| hours_stock_status | list[int] x 24 | 1 = out of stock in that hour |
| discount | float | Price ratio (1.0 = no discount) |
| holiday_flag, activity_flag | int | Holiday; promotion activity |
| precpt, avg_temperature, avg_humidity, avg_wind_level | float | Weather |

The train file holds 90 days and the eval file 7 days. The eval days are the official test split and are used once, for the final benchmark.

## Staged and quarantine

`edi.data_quality.checks` applies hard rules (row goes to quarantine with a reason) and soft rules (reported, row kept):

| Rule | Severity | Action |
|---|---|---|
| Required columns present, types coercible | hard | whole file fails if columns are missing |
| Required fields not null | hard | quarantine `null_required_field` |
| `hours_sale` and `hours_stock_status` have 24 entries | hard | quarantine `hours_sale_length` / `stock_status_length` |
| Stock status is 0 or 1 | hard | quarantine |
| `sale_amount` is finite and non-negative | hard | quarantine `negative_or_nonfinite_sale` |
| Discount within (0, 1] when present | hard | quarantine `discount_out_of_range` |
| Duplicate (store, product, day) | hard | keep first, quarantine the rest `duplicate_primary_key` |
| Discount null | soft | impute 1.0, set `discount_imputed = 1` |
| Daily sales equal the sum of hourly sales | soft | report the match rate |
| `stock_hour6_22_cnt` agrees with the hourly flags | soft | report the match rate; the hourly flags are used |
| Every series has every date | soft | report; gaps become explicit missing rows in the curated grid |

The fixture deliberately injects 4 duplicates, 2 null discounts, 1 negative sale and 1 malformed hourly list so that every rule is exercised. Results appear on the Data and reliability page.

## Curated

Built by `src/edi/sql/curated.sql` in DuckDB:

- `series_dim`: one row per store-product with identifiers, mean sales and the share of days with any stock-out.
- `calendar`: day index, date, holiday flag.
- `series_day`: a complete series x day grid. Missing or quarantined rows are present with `is_missing = 1`, so gaps are explicit rather than silently dropped. Includes `stockout_hours` (hours 06:00 to 22:00).
- `dq_daily_summary`: per-day counts used by the reliability page.

`edi.pipeline.load_panel` turns `series_day` into dense numpy arrays (`Panel`: series x day, plus series x day x 24 for hourly data). For the synthetic fixture, `Panel.latent` carries true demand so that recovery and forecast bias can be measured exactly. Real data has no such column.

## Derived

| File | Produced by | Contents |
|---|---|---|
| `data/curated/recovered_{A,B}.npy` | `edi forecast` | Demand estimate per series-day; equal to sales on fully stocked days, recovered from hourly profiles on stock-out days |
| `data/curated/forecasts_{A,B}.parquet` | `edi forecast` | Seven calibrated quantiles for horizons 1 to 5 from each forecast origin. Stage A fits on days up to 69 and calibrates on 70 to 76 (for tuning on 77 to 90); stage B fits up to 83 and calibrates on 84 to 90 (for the final test on 91 to 97). |
| `artifacts/forecast/metrics.json` | `edi forecast` | Accuracy, bias, coverage, and the controlled censoring experiment |
| `artifacts/benchmark/summary.json` | `edi benchmark`, `edi report` | Policy metrics with cluster-bootstrap intervals, paired differences, ablations, sensitivity, audit, hypotheses verdicts |
| `artifacts/benchmark/secondary_cloud.json` | `edi secondary` | Cloud capacity domain results |
| `artifacts/runs/<run_id>/` | every command | Manifest with config hash, git SHA, timings and output hashes |

## Decision contract

Every decision, from any domain or any external tool, reaches the validator as two records. JSON Schemas are exported to `schemas/` by `edi export-web`.

**`DecisionCandidate`** (what the proposing system claims): decision id, domain, entity, the data snapshot it used (id, age, missing history, state such as on-hand stock by age and inbound pipeline), the proposed action per resource, alternatives it considered, its objective, the constraints and financial assumptions it planned with, its forecast quantiles and its own scenario results (claimed expected cost and CVaR).

**`AuthoritativeContext`** (what the validator trusts): the current terms of record (resources, budget, minimum commitment), financial assumptions of record, approval threshold, maximum shares per resource, freshness limit, latest signals (for example yesterday's stock-out hours) and the cost of an investigation and a review.

The validator returns a **`ValidationReport`**: outcome (`recommend`, `investigate`, `defer`, `escalate`, `reject`), reasons, one result per gate (G1 to G7, each `pass`, `warn` or `fail` with evidence), a recommended action when it differs from the candidate, value-of-information details when relevant, and summary metrics. Hard failures are never averaged into a score.

All string fields have length limits, lists have size limits and numbers have ranges. Unknown fields are rejected.

## Assumption register

| Input | Kind |
|---|---|
| Sales, hourly sales, stock-out flags, discounts, weather, holidays | Observed (real data) or generated (fixture) |
| Demand on stock-out days | Estimated |
| Price, unit cost, holding, disposal, goodwill, shelf life by category | Assumed (configs/base.yaml) |
| Suppliers: lead times, costs, capacities, minimums, budget | Simulated |
| Disruptions, record errors, stale snapshots, late sales data | Simulated |
| Reviewer behavior (verification, re-planning, error rate) | Modeled |
| Investigation and review costs | Assumed |

The same register is shown on the Data and reliability page.
