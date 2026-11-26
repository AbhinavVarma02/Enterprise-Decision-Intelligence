"""Versioned decision contract shared by producers (policies, external systems) and the validator.

The schema is domain-neutral: an action is a vector of named resource quantities, and constraints are
resources with cost, capacity, minimum quantity, lead time and eligibility. Domain adapters interpret
the payload (inventory replenishment, cloud capacity). JSON Schema: schemas/decision_candidate.v1.json.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION: Final = "1.0"
Outcome = Literal["recommend", "investigate", "defer", "escalate", "reject"]
GateStatus = Literal["pass", "warn", "fail"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class Resource(_Strict):
    name: str = Field(min_length=1, max_length=40)
    lead_days: int = Field(ge=0, le=3)
    unit_cost: float = Field(gt=0, lt=1e6)
    capacity: float = Field(ge=0, lt=1e9)
    min_quantity: float = Field(default=0.0, ge=0)
    eligible: bool = True
    available: bool = True
    attributes: dict[str, float | str | bool] = Field(default_factory=dict)


class Constraints(_Strict):
    resources: list[Resource] = Field(min_length=1, max_length=8)
    budget: float = Field(ge=0)
    min_commitment: float = Field(default=0.0, ge=0)
    extra: dict[str, float] = Field(default_factory=dict)


class DataSnapshot(_Strict):
    snapshot_id: str = Field(min_length=1, max_length=80)
    as_of: str
    age_hours: float = Field(ge=0, le=24 * 365)
    history_days_missing: int = Field(default=0, ge=0, le=365)
    state: dict[str, list[float]] = Field(default_factory=dict)  # e.g. on_hand_by_age, pipeline_by_day


class ForecastDistribution(_Strict):
    model_version: str
    levels: list[float] = Field(min_length=3, max_length=21)
    quantiles: list[list[float]] = Field(min_length=1, max_length=31)  # horizon x levels

    @field_validator("levels")
    @classmethod
    def _levels_increasing(cls, v: list[float]) -> list[float]:
        if any(not 0 < x < 1 for x in v) or any(b <= a for a, b in zip(v, v[1:])):
            raise ValueError("levels must be strictly increasing within (0, 1)")
        return v

    @model_validator(mode="after")
    def _shape(self) -> ForecastDistribution:
        for row in self.quantiles:
            if len(row) != len(self.levels):
                raise ValueError("each quantile row must match levels")
            if any(x < 0 for x in row):
                raise ValueError("quantiles must be nonnegative")
        return self


class FinancialAssumptions(_Strict):
    currency: str = "USD (assumed)"
    price: float = Field(gt=0)
    unit_cost: float = Field(gt=0)
    holding: float = Field(ge=0)
    disposal: float = Field(ge=0)
    goodwill: float = Field(ge=0)
    shelf_life_days: int = Field(ge=1, le=60)
    terminal_waste_risk: float = Field(ge=0, le=1)


class Objective(_Strict):
    type: Literal["expected", "cvar", "deterministic", "rule", "external"]
    alpha: float | None = Field(default=None, gt=0, lt=1)
    lam: float | None = Field(default=None, ge=0, le=1)


class ScenarioResults(_Strict):
    expected_cost: float | None = None
    cvar: float | None = None
    n_scenarios: int = Field(default=0, ge=0)


class Alternative(_Strict):
    label: str = Field(max_length=60)
    action: dict[str, float]


class Entity(_Strict):
    entity_id: str = Field(max_length=80)
    label: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=40)
    typical_daily_volume: float = Field(gt=0)


class RiskTolerance(_Strict):
    cvar_alpha: float = Field(default=0.9, gt=0, lt=1)
    loss_tolerance: float | None = Field(default=None, ge=0)


class DecisionCandidate(_Strict):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    decision_id: str = Field(pattern=r"^[A-Za-z0-9_.:\-]{1,120}$")
    domain: Literal["inventory_replenishment", "cloud_capacity"]
    decision_day: int = Field(ge=0)
    decision_time: str
    entity: Entity
    data_snapshot: DataSnapshot
    action: dict[str, float]
    alternatives: list[Alternative] = Field(default_factory=list, max_length=12)
    objective: Objective
    constraints: Constraints
    forecast: ForecastDistribution | None = None
    financial_assumptions: FinancialAssumptions
    scenario_results: ScenarioResults | None = None
    model_version: str = "unknown"
    policy_version: str = "unknown"
    risk_tolerance: RiskTolerance = Field(default_factory=RiskTolerance)
    decision_status: Literal["proposed"] = "proposed"
    approval_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _action_matches_resources(self) -> DecisionCandidate:
        names = [r.name for r in self.constraints.resources]
        unknown = set(self.action) - set(names)
        if unknown:
            raise ValueError(f"action names {sorted(unknown)} are not declared resources")
        if any(v != v for v in self.action.values()):  # NaN
            raise ValueError("action quantities must be numbers")
        return self

    def action_vector(self) -> list[float]:
        return [float(self.action.get(r.name, 0.0)) for r in self.constraints.resources]


class AuthoritativeContext(_Strict):
    """What the validator trusts: master data of record, governance policy, latest signals."""

    constraints: Constraints
    financial_assumptions: FinancialAssumptions
    approval_threshold: float = Field(ge=0)
    max_share: dict[str, float] = Field(default_factory=dict)  # e.g. {"expedite": 0.6}
    freshness_max_age_hours: float = Field(default=30, gt=0)
    signals: dict[str, float] = Field(default_factory=dict)  # e.g. stockout_hours_yesterday
    investigation_cost: float = Field(default=0.0, ge=0)
    review_cost: float = Field(default=0.0, ge=0)


class GateResult(_Strict):
    gate: str
    name: str
    status: GateStatus
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(_Strict):
    decision_id: str
    outcome: Outcome
    reasons: list[str]
    gates: list[GateResult]
    recommended_action: dict[str, float] | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    value_of_information: dict[str, Any] | None = None
    explanation: str = ""
    validator_version: str = "edi-validator-1.0"
