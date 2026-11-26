# Third-party notices

This project's own code is MIT-licensed (see `LICENSE`). It uses the data and software below under their own licenses. Versions are the ones used to produce the committed artifacts; `requirements-lock.txt` and `apps/web/package-lock.json` hold the full resolved sets.

## Data

| Source | License | How it is used |
|---|---|---|
| FreshRetailNet-50K, Dingdong-Inc | CC BY 4.0 | The observed-data pilot uses revision `c374e85975c82816c495acfa904cc55ab14a47d3`. The project rescales publisher-normalized observations, estimates censored demand and publishes derived aggregates. The synthetic benchmark and browser cases use generated data. [Dataset source](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K/tree/c374e85975c82816c495acfa904cc55ab14a47d3) · [License](https://creativecommons.org/licenses/by/4.0/) |

Attribution for FreshRetailNet-50K: Dingdong-Inc, "FreshRetailNet-50K", https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K, licensed under CC BY 4.0. If you run the pipeline on it, keep this attribution with any results you publish.

Suppliers, prices, costs, disruptions and data faults are simulated by this project in every configuration. They are not taken from any company.

## Fonts

| Font | License | Notes |
|---|---|---|
| IBM Plex Sans (via `@fontsource/ibm-plex-sans` 5.3.0) | SIL Open Font License 1.1 | Latin subsets bundled into the static site. |
| IBM Plex Sans Condensed (via `@fontsource/ibm-plex-sans-condensed` 5.3.0) | SIL Open Font License 1.1 | Latin subsets bundled into the static site. |

## Web application runtime dependencies (shipped in the static bundle)

| Package | Version | License |
|---|---|---|
| react, react-dom, scheduler | 19.3.1, 19.3.1, 0.28.0 | MIT |
| react-router, react-router-dom | 7.18.7 | MIT |
| cookie, set-cookie-parser (react-router dependencies) | 1.1.1, 2.7.3 | MIT |
| d3-scale, d3-shape, d3-array, d3-color, d3-format, d3-interpolate, d3-path, d3-time, d3-time-format, internmap | 4.0.3, 3.2.1, 3.2.5, 3.1.1, 3.1.3, 3.0.2, 3.1.1, 3.1.1, 4.1.1, 2.0.3 | ISC |
| lucide-react | 1.80.0 | ISC |
| zod | 4.6.7 | MIT |

Build and test tooling (not shipped): TypeScript (Apache-2.0), Vite (MIT), Vitest (MIT), Playwright (Apache-2.0), axe-core and @axe-core/playwright (MPL-2.0), ESLint and typescript-eslint (MIT), jsdom (MIT), @testing-library/react (MIT).

## Python dependencies

Runtime:

| Package | Version | License |
|---|---|---|
| numpy | 2.5.5 | BSD-3-Clause (with bundled 0BSD, MIT, Zlib, CC0-1.0 components) |
| pandas | 3.1.1 | BSD-3-Clause |
| pyarrow | 26.0.1 | Apache-2.0 |
| duckdb | 2.0.1 | MIT |
| scipy (includes the HiGHS solver) | 1.18.1 | BSD-3-Clause; HiGHS is MIT |
| lightgbm | 4.7.0 | MIT |
| pydantic, pydantic-core | 2.14.4, 2.50.5 | MIT |
| PyYAML | 6.0.4 | MIT |
| python-dateutil | 4.0.0 | BSD-3-Clause |
| tzdata | 2026.6 | Apache-2.0 |
| annotated-types, typing-inspection | 0.8.0, 0.4.5 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |

Optional download extra: huggingface_hub (Apache-2.0), only needed to fetch FreshRetailNet-50K.

Development: pytest (MIT), hypothesis (MPL-2.0), ruff (MIT), mypy (MIT), pandas-stubs (BSD-3-Clause), types-PyYAML (Apache-2.0).

## Methods cited, not bundled

- Rockafellar, R. T. and Uryasev, S. (2000). Optimization of Conditional Value-at-Risk. Journal of Risk 2(3). Used for the mean-CVaR formulation.
- Split conformal prediction (Vovk, Gammerman and Shafer; Lei et al. 2018) for quantile calibration.
- Stockpyl (MIT) is discussed as a comparator in `docs/COMPETITIVE_ANALYSIS.md`; it is not a dependency.
