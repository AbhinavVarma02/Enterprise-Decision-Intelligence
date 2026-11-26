"""Shared plumbing: paths, config loading, hashing, atomic writes, structured logging, run manifests."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "1.0"


def repo_path(*parts: str) -> Path:
    return REPO_ROOT.joinpath(*parts)


# ---------------------------------------------------------------- logging


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, Mapping):
            payload.update(extra)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("EDI_LOG_LEVEL", "INFO"))
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, msg: str, **fields: Any) -> None:
    logger.info(msg, extra={"fields": fields})


# ---------------------------------------------------------------- config


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config. A config may name `extends: other.yaml` (relative to itself)."""
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = REPO_ROOT / path
    with path.open("r", encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh) or {}
    parent = cfg.pop("extends", None)
    if parent:
        cfg = _deep_merge(load_config(path.parent / parent), cfg)
    cfg["_config_path"] = str(path)
    return cfg


def config_hash(cfg: Mapping[str, Any]) -> str:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    return sha256_bytes(json.dumps(clean, sort_keys=True, default=str).encode())[:16]


# ---------------------------------------------------------------- hashing and io


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def hash_files(paths: Iterable[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.name).encode())
        h.update(sha256_file(p).encode())
    return h.hexdigest()[:16]


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; artifacts are meant to be shared
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def sanitize(obj: Any) -> Any:
    """Replace non-finite floats with None so JSON output stays standards-compliant."""
    import math

    import numpy as np

    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def write_json(path: Path, obj: Any, *, compact: bool = False) -> None:
    obj = sanitize(obj)
    if compact:
        text = json.dumps(obj, separators=(",", ":"), default=_json_default, allow_nan=False)
    else:
        text = json.dumps(obj, indent=2, default=_json_default, allow_nan=False)
    atomic_write_bytes(path, (text + "\n").encode("utf-8"))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _json_default(obj: Any) -> Any:
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def write_parquet(df: Any, path: Path) -> None:
    """Atomic parquet write via a temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
        )
        sha = out.stdout.strip() or "unknown"
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "configs"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Flag runs made from uncommitted code or configs, so a manifest never overstates provenance.
        return f"{sha}+dirty" if status.stdout.strip() else sha
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- run manifest


class Manifest:
    """Stage-level manifest that makes pipeline stages idempotent.

    A stage is skipped when its recorded input hash equals the current one and all of its
    outputs still exist.
    """

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = read_json(path) if path.exists() else {"stages": {}}

    def is_current(self, stage: str, input_hash: str) -> bool:
        rec = self.data["stages"].get(stage)
        if not rec or rec.get("input_hash") != input_hash:
            return False
        return all(Path(p).exists() for p in rec.get("outputs", []))

    def record(self, stage: str, input_hash: str, outputs: list[Path], **info: Any) -> None:
        self.data["stages"][stage] = {
            "input_hash": input_hash,
            "outputs": [str(p) for p in outputs],
            "completed_at": utc_now(),
            "git_sha": git_sha(),
            **info,
        }
        write_json(self.path, self.data)


def require_same_run(doc: dict[str, Any], cfg: dict[str, Any], what: str) -> None:
    """Refuse to combine artifacts from different configs (for example dev forecasts with research results).

    Forecast metrics and secondary-domain results live at fixed paths shared by every config, so a
    later run under another config silently replaces them. Each records the run name that wrote it.
    """
    found = doc.get("run_name")
    if found != cfg["run_name"]:
        raise RuntimeError(
            f"{what} was written by run '{found}', not '{cfg['run_name']}'. "
            f"Re-run that stage with this config before building reports."
        )
    if doc.get("config_hash") not in (None, config_hash(cfg)):
        raise RuntimeError(
            f"{what} was written with different settings for run '{found}'. Re-run that stage."
        )


def artifact_path(cfg: dict[str, Any], *parts: str) -> Path:
    """Path under this config's artifacts directory (``artifacts`` for research, separate for dev and ci)."""
    return repo_path(str(cfg.get("artifacts_dir", "artifacts")), *parts)
