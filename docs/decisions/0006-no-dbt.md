# ADR-0006: SQL in DuckDB via a Python runner instead of dbt

Status: accepted (2026-11-25). Deviation from the brief's suggested stack ("dbt-core, if justified").

Context. Five transformations, one database file, one developer.

Alternatives. dbt-core with dbt-duckdb; SQLMesh; plain SQL with a runner.

Decision. Plain SQL files executed by `edi.pipeline` with input hashing, atomic writes and a manifest.

Reasons. dbt adds a second project structure and dependency tree without adding capability at this size. Data tests are expressed as pytest and `edi.data_quality` checks, which also run in CI.

Trade-offs. No dbt docs site or lineage graph; lineage is recorded in the manifest and in `docs/DATA_MODEL.md`.
