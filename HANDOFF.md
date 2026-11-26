# Handoff

Updated 2026-11-26 America/New_York.

The observed-data audit is complete locally. `configs/research-real.yaml` reads the pinned official Parquet download in ignored `data/raw/freshretailnet/`, stages curated data in `data_real/` and publishes aggregate reports under `artifacts/real/`. `edi export-web --config configs/research-real.yaml` writes `research_evidence.json` alongside the historical synthetic benchmark and cases. The findings are in `docs/RELEASE_AUDIT.md`.

## Verification completed

The original and replayed real runs match for 31,500 forecast rows, 58,800 decision rows and 8,400 episode totals after excluding timing columns. Both independent study artifacts and original synthetic artifacts are retained. The test history and relevant changes are in `PROGRESS.md` and `CHANGELOG.md`. The audit did not rerun the full historical amendment 2 synthetic study. The current CI-sized synthetic pipeline and the alternate-domain experiment were executed locally.

## Publication status

The live Pages site serves source commit `6638da5ce64f5567d5c7358a3a0c91ec52d55248`. Production browser workflows, accessibility scans, security headers and byte equality for served JSON all passed. The next executable task after explicit authorization is GitHub publication followed by verification of the hosted Actions run. The pre-existing `Claude outputs/` files remain untracked. [Production](https://enterprise-decision-intelligence.pages.dev/)
