# ADR-0002: Schema-identical synthetic fixture while the dataset host is blocked

Status: accepted (2026-11-25)

Context. huggingface.co and its CDN returned HTTP 403 from the network proxy in both build shells, so FreshRetailNet-50K could not be downloaded during the build session.

Alternatives. (a) Stop until data is available; (b) use another dataset; (c) build against the real schema with a deterministic synthetic fixture and keep real-data runs as an explicit, one-command step.

Decision. (c). `edi.ingestion.synthetic` generates series with the exact FreshRetailNet-50K columns, censoring produced by a simulated shelf, plus a separate ground-truth latent demand table that real data does not have.

Reasons. Engineering and tests can proceed; the latent truth enables exact checks of recovery and leakage logic.

Trade-offs. Synthetic results say nothing about real retail behavior. They must never be presented as findings about the dataset.

Consequences and validation. Every artifact carries `data_source: synthetic_fixture | freshretailnet_50k`. The web app shows a persistent provenance banner when the source is synthetic. `PROGRESS.md` lists real-data experiments as not run.
