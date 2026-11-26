"""Value of information over a bounded action set.

For a discrete prior over an uncertain input (states j with probabilities p_j) and expected costs
C(a, j) for each action a in a finite set A:

    prior-optimal cost      V0 = min_a sum_j p_j C(a, j)
    perfect-information cost V1 = sum_j p_j min_a C(a, j)
    EVPI = V0 - V1 >= 0

When verification reveals the state exactly (an accurate cycle count reveals true on-hand), EVPI is
the exact value of that verification for this model. It is an upper bound for any imperfect check.
Results are exact for the stated prior and action set, and approximate for the underlying continuous
problem because A is a grid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VOIResult:
    evpi: float
    prior_optimal_cost: float
    perfect_information_cost: float
    prior_optimal_index: int
    best_index_by_state: list[int]
    probabilities: list[float]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "evpi": self.evpi,
            "prior_optimal_cost": self.prior_optimal_cost,
            "perfect_information_cost": self.perfect_information_cost,
            "prior_optimal_index": self.prior_optimal_index,
            "best_index_by_state": self.best_index_by_state,
            "probabilities": self.probabilities,
            "labels": self.labels,
            "method": "exact EVPI over a discrete prior and a bounded action grid",
        }


def evpi(costs: np.ndarray, probs: np.ndarray, labels: list[str] | None = None) -> VOIResult:
    """costs: (A, J) expected cost of action a in state j; probs: (J,) summing to 1."""
    costs = np.asarray(costs, dtype=float)
    probs = np.asarray(probs, dtype=float)
    if costs.ndim != 2 or costs.shape[1] != len(probs):
        raise ValueError("costs must be (actions, states) matching probs")
    if np.any(probs < 0) or abs(probs.sum() - 1) > 1e-9:
        raise ValueError("probabilities must be nonnegative and sum to 1")
    expected = costs @ probs
    a0 = int(np.argmin(expected))
    best_by_state = np.argmin(costs, axis=0)
    v1 = float(probs @ costs[best_by_state, np.arange(costs.shape[1])])
    v0 = float(expected[a0])
    return VOIResult(
        evpi=max(0.0, v0 - v1),
        prior_optimal_cost=v0,
        perfect_information_cost=v1,
        prior_optimal_index=a0,
        best_index_by_state=[int(i) for i in best_by_state],
        probabilities=[float(p) for p in probs],
        labels=labels or [f"state_{j}" for j in range(len(probs))],
    )
