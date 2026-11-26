# Design system

The web application is a decision workspace for planners, operations leaders and finance reviewers. Its job is to make one thing obvious on every decision: what the validator concluded, why, and what each option costs. Everything else stays quiet.

## Reference review

The author's earlier projects (Healthcare Payment Integrity, Patient Outreach Optimization) were reviewed in a browser on 2026-11-25 as a quality bar. Both use dark themes with large serif display headlines. This project deliberately takes a different identity: a light, daylight workspace, a single sans family in two widths, and the validator's verdict as the one bold typographic element.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--paper` | `#f5f6f4` | App background (cool neutral, not cream) |
| `--surface` | `#ffffff` | Panels, rail |
| `--ink` / `--ink-2` / `--ink-3` | `#1c2024` / `#4a535c` / `#5f6872` | Text hierarchy |
| `--line` / `--line-2` | `#dadfe3` / `#e9ecee` | Dividers, table rules |
| `--cobalt` | `#2742c4` | Structure: primary actions, selected navigation, the project's own series in charts |
| `--citrine` | `#e3b341` | The single accent: focus ring, selected option, recommended cell |
| Outcome colors | recommend `#1f7a4d`, investigate `#9a5800`, defer `#56606b`, escalate `#6a3fb5`, reject `#b3261e` | Semantic only: chips, verdict bar, gate marks |

All text and outcome colors pass WCAG AA contrast on their backgrounds (outcome foregrounds are used on their tinted backgrounds or white).

## Type

- **IBM Plex Sans** (400, 500, 600), self-hosted from `@fontsource` (OFL 1.1), Latin subset. Tabular, lining figures are on globally so amounts align in tables.
- **IBM Plex Sans Condensed** (500, 600) for table headers, gate identifiers and hypothesis IDs, where density matters.
- Scale: 12.5, 14, 15 (body), 16, 19, 23, 28, 34 px. Sentence case everywhere; no all-caps labels.

## Layout

- Left rail (236 px) with two groups: Decisions (overview, workspace, studio, history) and Evidence (benchmark, data, methodology). On screens under 860 px the rail becomes an off-canvas menu.
- Content column up to 1,320 px. Panels use a 12 px radius; chips and inputs use smaller radii so hierarchy shows in shape, not only size.
- The decision workspace is a dossier: verdict, then a two-column body (options and evidence on the left, gates, verification and the decision on the right).

## Components

- **Verdict**: an 8 px outcome-colored bar beside a 34 px headline ("Reject the proposed order") and a one-line reason. This is the only oversized type in the product.
- **Gate ledger**: seven rows, each with a pass, warning or fail mark (icon plus hidden text for screen readers) and the gate's evidence sentence.
- **Options table**: each option's order, expected cost, worst-10% average and a range bar (expected dot, 90th percentile tick, tail tick). Selecting a row explains the trade-off in a sentence.
- **Charts**: hand-built SVG with d3-scale and d3-shape. Each chart answers one question: forecast fan (what demand could be), stock by age (recorded versus physical), paired difference dot plot (which policy is cheaper than P3), coverage curve (how many decisions run automatically at each threshold), accuracy versus decision cost scatter (H1), cost heatmap (where the optimum sits).
- **States**: skeleton loading, explicit error panels that say what failed and how to fix it, empty states that point to the next action.

## Interaction and accessibility

- Every control is a native button, link, range input, checkbox or select. Keyboard focus shows a 3 px citrine outline. A skip link leads to the main content.
- Studio assumptions live in the URL query string, so a scenario can be bookmarked, shared or replayed from history.
- Motion is limited to the skeleton shimmer and the mobile menu slide; both are disabled under `prefers-reduced-motion`.
- Copy is written for business users: plain verbs, amounts with units, no internal identifiers unless they help (policy IDs are paired with names).

## Visual QA

`npm run screenshots` captures every page at 1440x900, 820x1180 and 390x844 into `docs/screenshots/`. The QA log for each refinement pass is in `docs/UI_REVIEW.md`.
