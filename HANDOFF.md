# Handoff

Updated 2026-11-26 America/New_York.

The observed-data audit is complete locally. `configs/research-real.yaml` reads the pinned official Parquet download in ignored `data/raw/freshretailnet/`, stages curated data in `data_real/` and publishes aggregate reports under `artifacts/real/`. `edi export-web --config configs/research-real.yaml` writes `research_evidence.json` alongside the historical synthetic benchmark and cases. The findings are in `docs/RELEASE_AUDIT.md`.

## Verification completed

The original and replayed real runs match for 31,500 forecast rows, 58,800 decision rows and 8,400 episode totals after excluding timing columns. Both independent study artifacts and original synthetic artifacts are retained. The test history and relevant changes are in `PROGRESS.md` and `CHANGELOG.md`. The audit did not rerun the full historical amendment 2 synthetic study. The current CI-sized synthetic pipeline and the alternate-domain experiment were executed locally.

## Publication status

The public GitHub repository tracks `main`. Hosted CI passed on Python 3.10, Python 3.13 and the web job for source commit `6bad18062584abd1b5b3f6d6ddadbcaac00daebc`. That commit is deployed on the existing Pages project. The final audit checked tracked paths, publishable Git history and all 29 served files. The local `Claude outputs/` folder is ignored. Release evidence and reproduction commands are linked from the README. [Repository](https://github.com/AbhinavVarma02/Enterprise-Decision-Intelligence) · [Hosted CI run](https://github.com/AbhinavVarma02/Enterprise-Decision-Intelligence/actions/runs/45876351092) · [Production](https://enterprise-decision-intelligence.pages.dev/)
