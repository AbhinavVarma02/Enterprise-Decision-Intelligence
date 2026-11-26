# AGENTS.md

Instructions for Codex, Claude Code and any other coding agent working in this repository.

## Project purpose

Enterprise Decision Intelligence is a vendor-independent reference implementation for evaluating the reliability of business decisions (not just predictions). The signature deliverable is the **Decision Reliability Benchmark**: a reproducible comparison of replenishment decision policies under normal operations, unreliable data and held-out disruptions, plus an independent validation engine that can recommend, investigate, defer, escalate or reject a candidate decision.

Primary domain: fresh-retail replenishment and procurement (FreshRetailNet-50K observations plus clearly labeled simulated operations). Secondary domain: cloud capacity reservation (synthetic).

## Mandatory reading order (every session)

1. `AGENTS.md` (this file) or `CLAUDE.md`
2. `MASTER_PROMPT.md` (canonical specification, never rewrite it; record deviations in `docs/decisions/`)
3. `PROGRESS.md`
4. `HANDOFF.md`, then `TASKS.md`
5. `git status` and `git log --oneline -15`
6. Verify the implementation (run the test commands below) instead of trusting the documents.
7. Resume the highest-priority incomplete task in `TASKS.md`.

Never reinitialize the repository, rebuild completed components or discard user changes.

## Repository structure

```
src/edi/            Python package (ingestion, data_quality, forecasting, simulation,
                    finance, optimization, validation, information_value, benchmark,
                    domains, integrations, explain, export, cli.py)
apps/web/           React + TypeScript + Vite application (Cloudflare Pages)
configs/            YAML experiment configs (dev.yaml, research.yaml)
schemas/            JSON Schemas generated from the Pydantic models
tests/              pytest suite (unit, property, integration)
artifacts/          Small versioned research outputs (JSON). Large outputs are ignored.
docs/               Research, architecture, methodology, ADRs (docs/decisions/), screenshots
data/               Local data lake (raw/staged/curated). Never committed except README.
scripts/            Helper scripts (dataset download, full reproduction)
```

## Commands

Python (3.10+):

```bash
uv venv && uv pip install -e ".[dev]"     # or: pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
mypy src
pytest -q
edi pipeline --config configs/dev.yaml     # ingest + validate + curate
edi forecast --config configs/dev.yaml
edi benchmark --config configs/dev.yaml
edi export-web --config configs/dev.yaml   # writes apps/web/public/data/*.json
edi run-all --config configs/dev.yaml      # everything above in order
```

Web:

```bash
cd apps/web
npm ci
npm run lint && npm run typecheck
npm test                 # vitest, includes Python golden-fixture parity
npm run build
npm run e2e              # Playwright
```

## Architectural constraints

- Python does heavy computation offline. The public site is static (Cloudflare Pages) with bounded browser-side calculation. No backend, no Pages Functions, no Workers.
- The browser evaluator searches a documented, bounded candidate-action space. It must match the Python reference evaluator on golden fixtures (`apps/web/src/engine/__fixtures__`). Never claim parity that is not tested.
- The validation engine must stay independent of the policies that generate candidates. It receives a `DecisionCandidate` (schemas/decision_candidate.v1.json) and authoritative context, never policy internals.
- Hard constraint failures are never hidden behind a score. Infeasible recommendations are never presented as valid.
- No future information inside any policy. Oracles are retrospective upper bounds only and are labeled as such.

## Budget restrictions

Zero incremental spend. No paid APIs, LLMs, hosting plans, fonts or component licenses. Do not enable paid Cloudflare features. Fonts are self-hosted OFL packages (@fontsource).

## Research integrity

- Label every number with its provenance: observed, estimated, simulated or assumed. The UI and docs must say when results come from the synthetic fixture.
- Real-data experiments are "not run" until actually executed on FreshRetailNet-50K. Do not copy synthetic results into real-data claims.
- Freeze `docs/EXPERIMENT_PROTOCOL.md` before final runs. Report negative findings.
- Never tune on the final test window (official eval split, days 91 to 97).
- Verify citations before adding them to `docs/RESEARCH.md`.

## Security rules

- No secrets in code, configs or the frontend bundle. Cloudflare credentials stay in the developer's local wrangler login.
- Validate and size-bound every imported file (1 MB limit in the browser). No `eval`, no `dangerouslySetInnerHTML` with untrusted data.
- Browser-local decision records are a demonstration. Never describe them as tamper-proof or compliant.

## UI quality expectations

Decision-centric workspace, not a KPI-card grid. Restrained palette, strong typography, precise financial formatting, keyboard access, visible focus, responsive layouts, real empty/error/loading states, no dead controls. Visual QA uses rendered screenshots (desktop, tablet, mobile), not source reading. See `docs/DESIGN_SYSTEM.md`.

## Completion criteria

A phase is complete only when its acceptance gate in `MASTER_PROMPT.md` section 24 passes with recorded evidence (test output, artifact path, screenshot). A failing material test blocks release.

## Maintaining progress files

After each meaningful milestone and before ending a session:

- `PROGRESS.md`: status, evidence, latest test results, next actions, last verified commit.
- `HANDOFF.md`: exact stopping point, changed files, commands run, blockers, next executable task.
- `TASKS.md`: update statuses.
- `CHANGELOG.md`: user-visible or research-relevant changes.
- `docs/decisions/`: add an ADR for any significant decision or deviation from `MASTER_PROMPT.md`.
