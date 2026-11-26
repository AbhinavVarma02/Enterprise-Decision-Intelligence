"""Download FreshRetailNet-50K and record provenance.

Usage:
    pip install huggingface_hub
    python scripts/download_freshretailnet.py [--revision <commit-sha>]

Writes data/raw/freshretailnet/ with the parquet files and PROVENANCE.json (resolved commit SHA,
SHA-256 per file, retrieval time). License: CC BY 4.0, attribution to Dingdong-Inc.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

REPO = "Dingdong-Inc/FreshRetailNet-50K"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "freshretailnet"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=None, help="dataset commit SHA to pin (default: latest)")
    args = parser.parse_args()
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install huggingface_hub") from exc

    info = HfApi().dataset_info(REPO, revision=args.revision)
    revision = info.sha
    local = snapshot_download(
        repo_id=REPO,
        repo_type="dataset",
        revision=revision,
        local_dir=OUT,
        allow_patterns=["*.parquet", "README.md"],
    )
    files = sorted(Path(local).rglob("*.parquet"))
    provenance = {
        "data_source": "freshretailnet_50k",
        "repo": REPO,
        "revision": revision,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "license": "CC BY 4.0",
        "attribution": "Dingdong-Inc, FreshRetailNet-50K; Wang et al., arXiv:2505.16319",
        "files": [{"path": str(f.relative_to(OUT)), "bytes": f.stat().st_size, "sha256": sha256(f)} for f in files],
    }
    (OUT / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"downloaded {len(files)} parquet files at revision {revision} into {OUT}")


if __name__ == "__main__":
    main()
