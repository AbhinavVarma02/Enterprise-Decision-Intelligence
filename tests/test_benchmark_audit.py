from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from edi.benchmark.report import harness_invariants, paired
from edi.benchmark.runner import violations
from edi.benchmark.validation_economics import breach_economics
from edi.finance.economics import base_supply_context, economics_for


def test_settlement_refuses_subminimum_and_respects_remaining_budget(base_cfg) -> None:
    econ = economics_for("fruit", base_cfg)
    supply = base_supply_context(20, econ, base_cfg, 91)
    supply = replace(supply, budget=econ.unit_cost * 5)
    flags, delivered = violations(np.array([20.0, 12.0, 0.0]), supply)
    assert flags == ["budget"]
    assert delivered[0] == 0
    assert delivered @ supply.unit_costs == pytest.approx(supply.budget)
    assert violations(delivered, supply)[0] == []
    flags, delivered = violations(np.array([1.0, 0.0, 0.0]), supply)
    assert flags == ["primary_moq"]
    assert not delivered.any()


def test_investigation_replan_reports_breaches() -> None:
    decisions = pd.DataFrame(
        [
            dict(
                series_id="s1_p1",
                day=91,
                policy="P5a",
                condition="unreliable",
                experiment="main",
                outcome="investigate",
                reviewer_note="",
                reviewed=False,
                governance_cost=2.0,
                exec_hard_violation=False,
            )
        ]
    )
    assert harness_invariants(decisions)["replanned_orders_checked"] == 1
    decisions["exec_hard_violation"] = True
    with pytest.raises(RuntimeError, match="harness invariant failed"):
        harness_invariants(decisions)


def test_paired_intervals_count_series_and_refuse_dropped_pairs() -> None:
    records = [
        (s, r, p, 2 + i if p == "a" else 1 + i, 1)
        for i, s in enumerate(("s1_p1", "s1_p2", "s2_p1"))
        for r in (0, 1)
        for p in ("a", "b")
    ]
    frame = pd.DataFrame(records, columns=["series_id", "realization", "policy", "total", "n_days"])
    result = paired(frame, "a", "b", 100, 4)
    assert result["diff_cost_per_day"] == {"mean": 1, "lo": 1, "hi": 1, "n": 3}
    assert result["crossed_store_product"]["n_store"] == result["crossed_store_product"]["n_product"] == 2
    with pytest.raises(ValueError, match="matched series"):
        paired(frame.iloc[:-1], "a", "b", 100, 4)


def test_incremental_breach_cost_counts_submissions_once() -> None:
    baseline = {"outcomes": {"execute": 100}, "hard_violation_rate": 0.1, "hard_violations": 14}
    validated = {"outcomes": {"recommend": 100}, "hard_violation_rate": 0, "hard_violations": 0}
    summary = {
        "meta": {"run_id": "test", "data_source": "synthetic_fixture"},
        "main": {"unreliable": {"P3": baseline, "P5a": validated}},
        "paired": {"unreliable": {"P5a_vs_P3": {"diff_cost_per_day": {"mean": 1}}}},
    }
    result = breach_economics(summary)
    assert result["break_even_per_breached_submission"] == 10
    assert result["sensitivity"][2]["validated_cost_minus_baseline_per_day"] == 0
