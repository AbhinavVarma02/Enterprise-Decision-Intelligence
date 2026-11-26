# Handoff

Updated 2026-11-26 America/New_York.

The observed-data audit is complete locally. `configs/research-real.yaml` reads the pinned official Parquet download in ignored `data/raw/freshretailnet/`, stages curated data in `data_real/` and publishes aggregate reports under `artifacts/real/`. `edi export-web --config configs/research-real.yaml` writes `research_evidence.json` alongside the historical synthetic benchmark and cases. The findings are in `docs/RELEASE_AUDIT.md`.

## Verification completed

The original and replayed real runs match for 31,500 forecast rows, 58,800 decision rows and 8,400 episode totals after excluding timing columns. Both independent study artifacts and original synthetic artifacts are retained. The test history and relevant changes are in `PROGRESS.md` and `CHANGELOG.md`. The audit did not rerun the full historical amendment 2 synthetic study. The current CI-sized synthetic pipeline and the alternate-domain experiment were executed locally.

## Remaining release work

Verify the final built assets and rendered screenshots, then deploy to the already-created `enterprise-decision-intelligence` Pages project. Run Playwright against the production URL and compare the served evidence JSON with the local build. Commit release evidence locally and record the deployment metadata. GitHub publication awaits explicit authorization. The pre-existing `Claude outputs/` files remain untracked.
