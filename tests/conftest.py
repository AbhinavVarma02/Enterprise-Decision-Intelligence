from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from edi.core import load_config
from edi.finance.economics import UnitEconomics, base_supply_context, economics_for


@pytest.fixture(scope="session")
def base_cfg() -> dict[str, Any]:
    return load_config("configs/ci.yaml")


@pytest.fixture(scope="session")
def pipeline_cfg(tmp_path_factory: pytest.TempPathFactory, base_cfg: dict[str, Any]) -> dict[str, Any]:
    """A tiny synthetic data lake in a temp directory, built once per session."""
    from edi import pipeline

    cfg = copy.deepcopy(base_cfg)
    cfg["data"]["dir"] = str(tmp_path_factory.mktemp("data"))
    cfg["data"]["source"] = "synthetic"
    pipeline.run(cfg, force=True)
    return cfg


@pytest.fixture(scope="session")
def panel(pipeline_cfg: dict[str, Any]):
    from edi.pipeline import load_panel

    return load_panel(pipeline_cfg)


@pytest.fixture()
def econ(base_cfg: dict[str, Any]) -> UnitEconomics:
    return economics_for("fruit", base_cfg)


@pytest.fixture()
def supply(base_cfg: dict[str, Any], econ: UnitEconomics):
    return base_supply_context(20.0, econ, base_cfg, 1)


@pytest.fixture()
def rng() -> np.random.Generator:
    return np.random.default_rng(12345)


ROOT = Path(__file__).resolve().parents[1]
