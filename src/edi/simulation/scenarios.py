"""Scenario generation: demand sampling from quantiles, disruptions and data faults.

Common random numbers: every draw that defines the world (event timing, magnitudes, faults) depends
only on (seed, series id, condition, realization), never on the policy. Policy-internal scenario
sampling uses separate streams keyed by (decision, purpose).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
from scipy.special import ndtr

DISRUPTIONS_TUNING = ("demand_spike", "capacity_reduction", "cost_increase")
DISRUPTIONS_HELDOUT = (
    "supplier_failure",
    "lead_time_increase",
    "transport_disruption",
    "budget_reduction",
    "demand_collapse",
    "combined",
)
FAULT_TYPES = ("inventory_record_error", "stale_supplier_snapshot", "stale_sales_history", "forecast_shift")


def stream(*keys: object) -> np.random.Generator:
    """Deterministic generator keyed by arbitrary values (stable across runs and platforms)."""
    h = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def quantile_function(q: np.ndarray, levels: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Piecewise-linear inverse CDF through the quantile knots, with linear tails to levels 0 and 1.

    Tail knots: Q(0) = max(0, 2 q_lo - q_next) and Q(1) = 2 q_hi - q_prev. The browser uses the same rule.
    """
    q = np.maximum.accumulate(np.asarray(q, dtype=float))
    lv = np.asarray(levels, dtype=float)
    q0 = max(0.0, 2 * q[0] - q[1])
    q1 = max(q[-1], 2 * q[-1] - q[-2])
    xs = np.concatenate([[0.0], lv, [1.0]])
    ys = np.concatenate([[min(q0, q[0])], q, [q1]])
    return np.maximum(np.interp(u, xs, ys), 0.0)


def sample_paths(
    quantiles: np.ndarray, levels: list[float], k: int, rho: float, rng: np.random.Generator
) -> np.ndarray:
    """Sample (k, H) demand paths. Days are linked by an equicorrelated Gaussian copula."""
    quantiles = np.atleast_2d(quantiles)
    n_h = quantiles.shape[0]
    z0 = rng.standard_normal((k, 1))
    e = rng.standard_normal((k, n_h))
    z = np.sqrt(rho) * z0 + np.sqrt(1 - rho) * e
    u = ndtr(z)
    lv = np.asarray(levels)
    return np.column_stack([quantile_function(quantiles[t], lv, u[:, t]) for t in range(n_h)])


@dataclass(frozen=True)
class Event:
    kind: str
    start: int
    end: int  # inclusive
    magnitude: float = 1.0

    def active(self, day: int) -> bool:
        return self.start <= day <= self.end


@dataclass
class WorldScenario:
    condition: str
    realization: int
    disruptions: list[Event] = field(default_factory=list)
    faults: list[Event] = field(default_factory=list)

    def labels(self) -> list[str]:
        return [e.kind for e in self.disruptions] + [f.kind for f in self.faults]

    def fault(self, kind: str, day: int) -> Event | None:
        for f in self.faults:
            if f.kind == kind and f.active(day):
                return f
        return None

    def disruption(self, kind: str, day: int) -> Event | None:
        for e in self.disruptions:
            if e.kind == kind and e.active(day):
                return e
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "condition": self.condition,
            "realization": self.realization,
            "disruptions": [e.__dict__ for e in self.disruptions],
            "faults": [f.__dict__ for f in self.faults],
        }


def make_world(
    seed: int, series_id: str, condition: str, realization: int, window: tuple[int, int], phase: str, fault_rate: float
) -> WorldScenario:
    """Draw the world for one (series, condition, realization). phase is 'tuning' or 'test'."""
    ws, we = window
    rng = stream(seed, series_id, condition, realization, phase)
    world = WorldScenario(condition=condition, realization=realization)
    last_start = max(ws, we - 2)
    if condition == "normal":
        return world
    if condition == "disruption":
        pool = DISRUPTIONS_TUNING if phase == "tuning" else DISRUPTIONS_HELDOUT
        kind = str(pool[int(rng.integers(len(pool)))])
        s = int(rng.integers(ws, last_start + 1))
        kinds = ["supplier_failure", "demand_spike", "budget_reduction"] if kind == "combined" else [kind]
        for k in kinds:
            world.disruptions.append(_disruption(k, s, we, rng))
        return world
    if condition == "unreliable":
        drawn = [f for f in FAULT_TYPES if rng.random() < fault_rate]
        if not drawn:
            others = FAULT_TYPES[1:]
            drawn = [str(others[int(rng.integers(len(others)))])]
        for f in drawn:
            s = int(rng.integers(ws, last_start + 1))
            world.faults.append(_fault(f, s, we, rng))
        return world
    raise ValueError(f"unknown condition {condition}")


def _disruption(kind: str, s: int, we: int, rng: np.random.Generator) -> Event:
    if kind == "supplier_failure":
        return Event(kind, s, min(we, s + 2))
    if kind == "lead_time_increase":
        return Event(kind, s, min(we, s + 3), 1.0)
    if kind == "capacity_reduction":
        return Event(kind, s, min(we, s + 3), 0.4)
    if kind == "cost_increase":
        return Event(kind, s, we, 1.25)
    if kind == "transport_disruption":
        return Event(kind, s, min(we, s + 3))
    if kind == "budget_reduction":
        return Event(kind, s, we, 0.5)
    if kind == "demand_spike":
        return Event(kind, s, min(we, s + 1), 1.6)
    if kind == "demand_collapse":
        return Event(kind, s, min(we, s + 2), 0.5)
    raise ValueError(kind)


def _fault(kind: str, s: int, we: int, rng: np.random.Generator) -> Event:
    if kind == "inventory_record_error":
        length = int(rng.integers(2, 5))
        return Event(kind, s, min(we, s + length - 1), float(1.0 + rng.uniform(0.5, 2.0)))
    if kind == "stale_supplier_snapshot":
        # magnitude encodes which master-data change the planning snapshot misses
        return Event(kind, s, min(we, s + 2), float(int(rng.integers(3))))
    if kind == "stale_sales_history":
        return Event(kind, s, min(we, s + 2), 2.0)
    if kind == "forecast_shift":
        return Event(kind, s, we, 1.35)
    raise ValueError(kind)
