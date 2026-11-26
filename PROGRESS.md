# Progress

Updated 2026-11-26 America/New_York.

| Area | Status and evidence |
|---|---|
| Observed data | Official pinned FreshRetailNet files downloaded and audited. All 4.85 million source rows scanned for partition counts, duplicates and stockout consistency. The 60-series subset retained 5,820 rows. `artifacts/real/dataset_audit.json` |
| Research pilot | Main run `research-real-fedd353b9ef7b1d1` completed with 58,800 simulated decisions. Forecasts, decision rows and episode totals reproduced exactly excluding timing fields. Independent selective replay completed with 7,560 decisions. `artifacts/real/` |
| Synthetic benchmark | Historical amendment 2 remains intact. Headline metrics were reconciled with the committed aggregate and the current synthetic CI-sized pipeline completed locally. `docs/BENCHMARK_FINDINGS.md` |
| Independent audit | Corrected volume-scale leakage, split preservation, simulation fulfillment, matching of reviewer draws, grid feasibility, resource ordering, browser decisions and history integrity. `docs/RELEASE_AUDIT.md` |
| Cloud capacity | Re-executed the secondary synthetic experiment with the 40-path audit configuration. The reusable contract and shared statistical methods are documented. |
| Engineering | 65 Python tests and 42 web tests pass. Ruff, mypy, ESLint and TypeScript pass. Playwright passed 16 production workflows and 21 axe scans. Captured and inspected 21 screenshots. Build 30 files, approximately 1.05 MB. |
| Cloudflare Pages | Production routes, headers and eight served JSON files verified. [Live site](https://enterprise-decision-intelligence.pages.dev/) |
| GitHub | Publication authorized. Release review includes the Git history, tracked artifacts, hosted workflows and the existing Pages site. |

Deployed and verified source commit `6638da5ce64f5567d5c7358a3a0c91ec52d55248`. The full replay ran with `20bcd78+dirty` while validation hardening was being developed. Its numerical results matched the first corrected pilot exactly.
