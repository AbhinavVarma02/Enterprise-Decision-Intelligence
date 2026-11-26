# Security and threat model

The deployed product is a static site: HTML, JavaScript, fonts and precomputed JSON served from a CDN. There is no server code, no database, no authentication and no secret anywhere in the build. The Python side runs offline on a developer's machine. This document lists what can still go wrong and what the code does about it.

## Assets worth protecting

| Asset | Where it lives | Why it matters |
|---|---|---|
| Integrity of published results | `apps/web/public/data/*.json`, `artifacts/` | Readers rely on the numbers being the ones the pipeline produced. |
| The visitor's browser | the static site | A static site can still run hostile script if it renders untrusted content unsafely. |
| The visitor's local decision log | `localStorage` key in the visitor's browser | Users may type notes. It is theirs, and it is not sent anywhere. |
| The developer's machine | Python pipeline, download script | It reads downloaded data and user-supplied configs. |

## Trust boundaries and controls

**1. Data entering the Python pipeline (downloaded parquet, configs).**
- `scripts/download_freshretailnet.py` downloads only from the fixed Hugging Face dataset id, writes only to `data/raw/freshretailnet/`, and records the resolved revision SHA and a SHA-256 per file.
- Ingestion validates schema and types; rows that break hard rules are quarantined with a reason instead of being silently fixed (`src/edi/data_quality/checks.py`).
- Config files are parsed with `yaml.safe_load`. There is no `eval`, `exec`, `pickle` or dynamic import of user-provided paths anywhere in `src/`.
- Workloads are bounded: series counts, scenario counts and realizations come from config, each MILP solve has a 10-second time limit, and the simulator caps the decision horizon (`MAX_HORIZON = 4`).
- DuckDB SQL is a fixed file (`src/edi/sql/curated.sql`) with no string-built queries from data values.

**2. Decision records crossing a system boundary (validator API, mock ERP adapter).**
- All inbound records are pydantic models with `extra="forbid"`, length limits on every string, bounded list sizes and numeric ranges (`src/edi/validation/schema.py`, `src/edi/integrations/mock_erp.py`). Identifiers use a restrictive pattern, so a value like `../../etc/passwd` is rejected (tested).
- The mock ERP adapter never sends anything. `to_purchase_order` returns a document marked `"simulated": true` and raises unless the validator recommended the requisition or a named approver is supplied.

**3. Files a visitor loads into the browser (decision-log import, decision bundle import).**
- Size is checked before reading (1 MB limit).
- Content is parsed with `JSON.parse` and validated with zod schemas that bound every string, array and number. Anything that does not match is rejected with a message; nothing partial is written.
- An imported log is re-hashed and the chain verified before it replaces the current log.
- Rendering never uses `dangerouslySetInnerHTML`; an ESLint rule forbids it. React escapes all text, so a note or label containing markup is shown as text.

**4. The static site itself.**
- `apps/web/public/_headers` sets a strict Content-Security-Policy: scripts only from the site's own origin, no inline script, no `eval`, `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `form-action 'none'`. Inline styles are allowed because React sets `style` attributes for chart geometry.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, a restrictive `Permissions-Policy` and `Cross-Origin-Opener-Policy: same-origin`.
- No third-party requests: fonts are self-hosted, there is no analytics, no CDN script and no external API.
- `apps/web/scripts/check-size.mjs` fails the build if the output exceeds 3 MB, any single file exceeds 1 MB, there are more than 100 files, or a `functions/` directory appears (which would turn the static site into server code on Cloudflare Pages).

**5. Secrets.**
- There are none to leak: no API keys, tokens or credentials are needed at build or run time. Deployment uses the developer's own `wrangler login` session, which never enters the repository.
- `.gitignore` excludes `.env*`, `data/`, `artifacts/runs/` and other local state.

## What the browser decision log is, and is not

Each record stores the SHA-256 of the previous record, so accidental edits or truncation are detectable, and the History page shows whether the chain is intact. This is **not** tamper-proof: anyone with access to the browser can rewrite the whole chain consistently, and clearing site data deletes it. It is a convenience for demonstrating replay and audit trails, not a compliance record. The UI says so.

## Known gaps

- Cloudflare Pages serves `_headers` only when deployed there; other static hosts need equivalent headers configured.
- The CSP keeps `style-src 'unsafe-inline'`. Removing it would require moving all chart geometry into CSS classes or SVG attributes; React's `style` prop does not use inline `<style>` blocks, so the practical risk is low, but it is still a relaxation.
- Dependency scanning: CI runs `npm audit --omit=dev` on the shipped web packages. Python packages are not scanned in CI; on 2026-11-26 `pip-audit` over the installed environment (the versions in `requirements-lock.txt`) and `npm audit --omit=dev` both reported no known vulnerabilities. Re-run both before deploying.
- The download script trusts Hugging Face's TLS and the dataset publisher. It records hashes so later runs can detect a changed upstream file, but it cannot tell whether the first download was genuine.

## Reporting

This is a portfolio project without a security contact. Open an issue on the repository for anything that looks wrong.
