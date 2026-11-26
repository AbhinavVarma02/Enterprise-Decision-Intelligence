# data/

Local data lake. Nothing here is committed except this file.

```
data/raw/freshretailnet/      train.parquet, eval.parquet, PROVENANCE.json (revision SHA, SHA-256, retrieval time)
data/raw/synthetic/           generated fixture + latent_demand.parquet (ground truth, synthetic only)
data/staged/                  typed, standardized rows
data/quarantine/              rows failing hard checks, with reason codes
data/curated/                 profiles, recovered demand, features, forecasts
data/edi.duckdb               DuckDB views over the parquet layers
```

Get the real dataset (CC BY 4.0, Dingdong-Inc) on a machine that can reach huggingface.co:

```bash
pip install huggingface_hub
python scripts/download_freshretailnet.py            # pins and records the resolved revision
edi run-all --config configs/research.yaml
```

Attribution: FreshRetailNet-50K by Dingdong-Inc, https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K, licensed CC BY 4.0. Values of `sale_amount` and `hours_sale` are normalized by the publisher; currency amounts in this project are assumptions applied to those normalized units.
