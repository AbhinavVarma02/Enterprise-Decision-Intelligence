# ADR-0001: Offline Python research, static web application

Status: accepted (2026-11-25)

Context. The brief requires zero incremental cost, Cloudflare Pages hosting and credible optimization and benchmarking.

Alternatives. (a) Python backend on a paid or free-tier server; (b) Pages Functions or Workers running calculations; (c) offline Python plus a static site with bounded browser computation.

Decision. (c). Python runs ingestion, forecasting, MILP policies, simulation and the benchmark locally. The site serves versioned JSON and evaluates a bounded action grid in TypeScript.

Reasons. No runtime cost or quota risk, no secrets on the server, reproducible artifacts, fast pages.

Trade-offs. The browser cannot run the MILP or the full benchmark. Two implementations of the evaluator and gates must agree.

Consequences and validation. Golden fixtures exported by Python are asserted in vitest (`npm test`). The UI labels browser results as "bounded grid search" and precomputed results as "offline benchmark".
