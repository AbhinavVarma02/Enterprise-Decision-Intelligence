"""Assumed unit economics, supplier menus and cost accounting.

All amounts are assumptions applied to (normalized) units. Cost convention:

    total cost = procurement + holding + disposal + lost revenue (full price per unit short)
                 + goodwill penalty + governance (investigation, review)

Lost sales are charged at the full unit price, not margin: the purchase cost of a unit that was
never bought is already absent from procurement spend, so charging margin would understate the
shortage. With this convention `total cost = price x demand - profit`, where
profit = revenue - procurement - holding - disposal - goodwill - governance - terminal adjustment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

import numpy as np

SUPPLIER_NAMES = ("primary", "alternate", "expedite")


@dataclass(frozen=True)
class UnitEconomics:
    price: float
    unit_cost: float
    shelf_life: int
    holding: float
    disposal: float
    goodwill: float
    terminal_waste_risk: float

    @property
    def shortage_cost(self) -> float:
        return self.price + self.goodwill

    @property
    def terminal_charge(self) -> float:
        """Per-unit value adjustment for stock left at the end of an evaluation horizon.

        Leftover units are credited at their expected replacement value, (1 - r) x unit cost, less the
        expected disposal r x disposal and one more night of holding, where r is the assumed chance the
        unit eventually spoils. The charge is therefore usually negative (a credit). Ordering one extra
        unit that ends up left over costs unit cost + charge = r x (unit cost + disposal) + holding, the
        expected overage cost. A positive charge would wrongly make wasting old stock look cheaper than
        carrying fresh stock.
        """
        r = self.terminal_waste_risk
        return r * (self.unit_cost + self.disposal) + self.holding - self.unit_cost

    def to_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def economics_for(profile: str, cfg: dict[str, Any]) -> UnitEconomics:
    p = cfg["economics"]["profiles"][profile]
    return UnitEconomics(
        price=float(p["price"]),
        unit_cost=float(p["unit_cost"]),
        shelf_life=int(p["shelf_life"]),
        holding=float(p["holding"]),
        disposal=float(p["disposal"]),
        goodwill=float(p["goodwill"]),
        terminal_waste_risk=float(p["terminal_waste_risk"]),
    )


@dataclass(frozen=True)
class Supplier:
    name: str
    lead: int
    unit_cost: float
    capacity: float
    moq: float = 0.0
    eligible: bool = True
    available: bool = True

    @property
    def usable_capacity(self) -> float:
        return self.capacity if (self.eligible and self.available) else 0.0


@dataclass(frozen=True)
class SupplyContext:
    """Supplier menu, budget and governance limits for one decision."""

    suppliers: tuple[Supplier, Supplier, Supplier]
    budget: float
    approval_threshold: float
    max_expedite_share: float
    as_of_day: int
    snapshot_id: str = "authoritative"
    min_commitment: float = 0.0
    max_expected_shortage: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def leads(self) -> np.ndarray:
        return np.array([s.lead for s in self.suppliers], dtype=int)

    @property
    def unit_costs(self) -> np.ndarray:
        return np.array([s.unit_cost for s in self.suppliers], dtype=float)

    @property
    def capacities(self) -> np.ndarray:
        return np.array([s.usable_capacity for s in self.suppliers], dtype=float)

    @property
    def moqs(self) -> np.ndarray:
        return np.array([s.moq for s in self.suppliers], dtype=float)

    def with_supplier(self, name: str, **changes: Any) -> SupplyContext:
        sup = tuple(replace(s, **changes) if s.name == name else s for s in self.suppliers)
        return replace(self, suppliers=sup)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suppliers": [asdict(s) for s in self.suppliers],
            "budget": self.budget,
            "approval_threshold": self.approval_threshold,
            "max_expedite_share": self.max_expedite_share,
            "as_of_day": self.as_of_day,
            "snapshot_id": self.snapshot_id,
            "min_commitment": self.min_commitment,
            "max_expected_shortage": self.max_expected_shortage,
        }


def base_supply_context(mu: float, econ: UnitEconomics, cfg: dict[str, Any], day: int) -> SupplyContext:
    """Supplier menu scaled to the series' typical daily demand `mu` (assumed parameters)."""
    sc = cfg["suppliers"]
    sups = []
    for name in SUPPLIER_NAMES:
        s = sc[name]
        sups.append(
            Supplier(
                name=name,
                lead=int(s["lead"]),
                unit_cost=econ.unit_cost * float(s["cost_mult"]),
                capacity=mu * float(s["capacity_mult"]),
                moq=mu * float(s["moq_mult"]),
            )
        )
    gov = cfg["governance"]
    return SupplyContext(
        suppliers=(sups[0], sups[1], sups[2]),
        budget=float(sc["budget_mult"]) * mu * econ.unit_cost,
        approval_threshold=float(gov["approval_spend_mult"]) * mu * econ.unit_cost,
        max_expedite_share=float(gov["max_expedite_share"]),
        as_of_day=day,
    )


@dataclass
class CostBreakdown:
    procurement: float = 0.0
    holding: float = 0.0
    disposal: float = 0.0
    lost_revenue: float = 0.0
    goodwill: float = 0.0
    governance: float = 0.0
    terminal_adjustment: float = 0.0  # value adjustment for stock left at the end (usually a credit)
    revenue: float = 0.0
    demand_units: float = 0.0
    sales_units: float = 0.0
    lost_units: float = 0.0
    waste_units: float = 0.0
    received_units: float = 0.0
    inventory_value_days: float = 0.0  # sum over days of end-of-day inventory at cost
    days: int = 0

    @property
    def total(self) -> float:
        return (
            self.procurement
            + self.holding
            + self.disposal
            + self.lost_revenue
            + self.goodwill
            + self.governance
            + self.terminal_adjustment
        )

    @property
    def profit(self) -> float:
        return (
            self.revenue
            - self.procurement
            - self.holding
            - self.disposal
            - self.goodwill
            - self.governance
            - self.terminal_adjustment
        )

    def add(self, other: CostBreakdown) -> None:
        for k in asdict(other):
            setattr(self, k, getattr(self, k) + getattr(other, k))

    def to_dict(self) -> dict[str, float]:
        d = {k: float(v) for k, v in asdict(self).items()}
        d["total"] = float(self.total)
        d["profit"] = float(self.profit)
        return d
