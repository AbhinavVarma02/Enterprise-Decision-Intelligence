"""Verify the pinned download and record full-partition data-quality counts."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from edi.core import artifact_path, load_config, read_json, sha256_file, write_json
from edi.ingestion.freshretailnet import find_split_files
from edi.pipeline import layout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/research-real.yaml"))
    cfg = load_config(parser.parse_args().config)
    root = layout(cfg).raw_real
    provenance = read_json(root / "PROVENANCE.json")
    if provenance["revision"] != cfg["data"]["freshretailnet"]["revision"]:
        raise ValueError("downloaded revision differs from the research configuration")
    expected = {f["path"].replace("\\", "/"): f["sha256"] for f in provenance["files"]}
    partitions = find_split_files(root)
    rows = {}
    with duckdb.connect(config={"threads": 4}) as con:
        for split, paths in partitions.items():
            for path in paths:
                if sha256_file(path) != expected[path.relative_to(root).as_posix()]:
                    raise ValueError(f"checksum mismatch for {path.name}")
            con.read_parquet([str(p) for p in paths]).create_view(split)
            audit = con.sql(f"""
                SELECT count(*) AS rows, count(DISTINCT dt) AS dates, min(dt) AS first_date, max(dt) AS last_date,
                       count(DISTINCT (store_id, product_id)) AS store_products, count(DISTINCT city_id) AS cities,
                       count(DISTINCT store_id) AS stores, count(DISTINCT product_id) AS products,
                       count(*) - count(DISTINCT (store_id, product_id, dt)) AS duplicate_keys,
                       count(*) FILTER (WHERE stock_hour6_22_cnt > 0) AS stockout_days,
                       count(*) FILTER (WHERE length(hours_sale) IS DISTINCT FROM 24
                                          OR length(hours_stock_status) IS DISTINCT FROM 24) AS malformed_hours,
                       count(*) FILTER (WHERE list_sum(list_slice(hours_stock_status, 7, 22))
                                          IS DISTINCT FROM stock_hour6_22_cnt) AS count_mismatch_6_to_21,
                       count(*) FILTER (WHERE list_sum(list_slice(hours_stock_status, 7, 23))
                                          IS DISTINCT FROM stock_hour6_22_cnt) AS count_mismatch_6_to_22
                FROM {split}
            """).df()
            rows[split] = audit.iloc[0].to_dict()
        train_only, eval_only = con.sql("""
            WITH a AS (SELECT DISTINCT store_id, product_id FROM train),
                 b AS (SELECT DISTINCT store_id, product_id FROM eval)
            SELECT (SELECT count(*) FROM a ANTI JOIN b USING (store_id, product_id)),
                   (SELECT count(*) FROM b ANTI JOIN a USING (store_id, product_id))
        """).fetchall()[0]
    path = artifact_path(cfg, "dataset_audit.json")
    write_json(
        path,
        {
            "provenance": provenance,
            "partitions": rows,
            "train_only_pairs": train_only,
            "eval_only_pairs": eval_only,
        },
    )
    print(path)


if __name__ == "__main__":
    main()
