"""Inventory replenishment adapter for the validation engine, plus candidate construction helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

from edi.finance.economics import SupplyContext, Supplier, UnitEconomics
from edi.optimization.milp import action_grid
from edi.simulation.engine import evaluate_actions, horizon_for
from edi.simulation.scenarios import sample_paths
from edi.validation.engine import ValidatorParams
from edi.validation.schema import (
    AuthoritativeContext,
    Constraints,
    DataSnapshot,
    DecisionCandidate,
    Entity,
    FinancialAssumptions,
    ForecastDistribution,
    Objective,
    Resource,
    RiskTolerance,
    ScenarioResults,
)

RESOURCES = ("primary", "alternate", "expedite")


def econ_from(fa: FinancialAssumptions) -> UnitEconomics:
    return UnitEconomics(
        price=fa.price,
        unit_cost=fa.unit_cost,
        shelf_life=fa.shelf_life_days,
        holding=fa.holding,
        disposal=fa.disposal,
        goodwill=fa.goodwill,
        terminal_waste_risk=fa.terminal_waste_risk,
    )


def assumptions_from(econ: UnitEconomics, currency: str = "USD (assumed)") -> FinancialAssumptions:
    return FinancialAssumptions(
        currency=currency,
        price=econ.price,
        unit_cost=econ.unit_cost,
        holding=econ.holding,
        disposal=econ.disposal,
        goodwill=econ.goodwill,
        shelf_life_days=econ.shelf_life,
        terminal_waste_risk=econ.terminal_waste_risk,
    )


def constraints_from(sup: SupplyContext) -> Constraints:
    return Constraints(
        resources=[
            Resource(
                name=s.name,
                lead_days=s.lead,
                unit_cost=s.unit_cost,
                capacity=s.capacity,
                min_quantity=s.moq,
                eligible=s.eligible,
                available=s.available,
            )
            for s in sup.suppliers
        ],
        budget=sup.budget,
        min_commitment=sup.min_commitment,
    )


def supply_from(c: Constraints, approval_threshold: float = float("inf"), max_expedite_share: float = 1.0) -> SupplyContext:
    by = {r.name: r for r in c.resources}
    sups = tuple(
        Supplier(
            name=n,
            lead=by[n].lead_days,
            unit_cost=by[n].unit_cost,
            capacity=by[n].capacity,
            moq=by[n].min_quantity,
            eligible=by[n].eligible,
            available=by[n].available,
        )
        for n in RESOURCES
    )
    return SupplyContext(
        suppliers=sups,  # type: ignore[arg-type]
        budget=c.budget,
        approval_threshold=approval_threshold,
        max_expedite_share=max_expedite_share,
        as_of_day=0,
        min_commitment=c.min_commitment,
    )


def build_candidate(
    *,
    decision_id: str,
    day: int,
    decision_time: str,
    series_id: str,
    category: str,
    mu: float,
    orders: np.ndarray,
    snapshot_supply: SupplyContext,
    econ: UnitEconomics,
    cohorts: np.ndarray,
    pipeline: np.ndarray,
    forecast_q: np.ndarray | None,
    levels: list[float],
    model_version: str,
    policy_version: str,
    objective: str,
    expected_cost: float | None,
    cvar_value: float | None,
    n_scenarios: int,
    age_hours: float,
    history_days_missing: int,
    snapshot_id: str,
    alpha: float = 0.9,
    lam: float | None = None,
) -> DecisionCandidate:
    fc = None
    if forecast_q is not None:
        fc = ForecastDistribution(
            model_version=model_version,
            levels=list(levels),
            quantiles=[[float(max(0.0, x)) for x in row] for row in np.asarray(forecast_q)],
        )
    return DecisionCandidate(
        decision_id=decision_id,
        domain="inventory_replenishment",
        decision_day=day,
        decision_time=decision_time,
        entity=Entity(entity_id=series_id, label=series_id, category=category, typical_daily_volume=max(mu, 1e-6)),
        data_snapshot=DataSnapshot(
            snapshot_id=snapshot_id,
            as_of=decision_time,
            age_hours=age_hours,
            history_days_missing=history_days_missing,
            state={
                "on_hand_by_age": [float(x) for x in cohorts],
                "pipeline_by_day": [float(x) for x in pipeline],
            },
        ),
        action={n: float(q) for n, q in zip(RESOURCES, orders)},
        objective=Objective(type=objective if objective in ("expected", "cvar", "deterministic", "rule") else "external",  # type: ignore[arg-type]
                            alpha=alpha if objective == "cvar" else None, lam=lam),
        constraints=constraints_from(snapshot_supply),
        forecast=fc,
        financial_assumptions=assumptions_from(econ),
        scenario_results=ScenarioResults(expected_cost=expected_cost, cvar=cvar_value, n_scenarios=n_scenarios)
        if expected_cost is not None
        else None,
        model_version=model_version,
        policy_version=policy_version,
        risk_tolerance=RiskTolerance(cvar_alpha=alpha),
    )


class InventoryAdapter:
    name = "inventory_replenishment"

    def required_state(self) -> list[str]:
        return ["on_hand_by_age", "pipeline_by_day"]

    def revenue_scale(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> float:
        return float(cand.entity.typical_daily_volume * ctx.financial_assumptions.price)

    def _supply(self, ctx: AuthoritativeContext) -> SupplyContext:
        return supply_from(ctx.constraints)

    def horizon(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> int:
        sup = self._supply(ctx)
        n_rows = len(cand.forecast.quantiles) if cand.forecast else 2
        return int(min(n_rows, horizon_for(sup.leads, sup.capacities)))

    def scenarios(self, cand: DecisionCandidate, k: int, rho: float, rng: np.random.Generator) -> np.ndarray:
        assert cand.forecast is not None
        return sample_paths(np.array(cand.forecast.quantiles), cand.forecast.levels, k, rho, rng)

    def evaluate(
        self,
        cand: DecisionCandidate,
        ctx: AuthoritativeContext,
        actions: np.ndarray,
        scenarios: np.ndarray,
        state: dict[str, Any] | None = None,
        terms: str = "authoritative",
    ) -> np.ndarray:
        """Expected-cost evaluation. terms='candidate' uses the candidate's own stated prices and leads."""
        if terms == "candidate":
            econ = econ_from(cand.financial_assumptions)
            sup = supply_from(cand.constraints)
        else:
            econ = econ_from(ctx.financial_assumptions)
            sup = self._supply(ctx)
        h = self.horizon(cand, ctx)
        st = state or {}
        cohorts = np.asarray(st.get("on_hand_by_age", cand.data_snapshot.state["on_hand_by_age"]), dtype=float)
        pipe = np.asarray(cand.data_snapshot.state["pipeline_by_day"], dtype=float)
        pipe_h = np.zeros(h)
        pipe_h[: min(h, len(pipe))] = pipe[:h]
        acts = np.minimum(np.atleast_2d(actions), sup.capacities[None, :])  # undeliverable units never arrive
        if len(cohorts) != econ.shelf_life:
            cohorts = np.resize(cohorts, econ.shelf_life)
        return evaluate_actions(cohorts, pipe_h, acts, sup.leads, sup.unit_costs, scenarios[:, :h], econ).cost

    def grid(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> np.ndarray:
        sup = self._supply(ctx)
        return action_grid(sup, self.horizon(cand, ctx))

    def stress_cases(self, cand: DecisionCandidate, ctx: AuthoritativeContext, scenarios: np.ndarray) -> list[tuple[str, Any]]:
        def primary_fails(acts: np.ndarray) -> np.ndarray:
            a = np.atleast_2d(acts).copy()
            a[:, 0] = 0.0
            return self.evaluate(cand, ctx, a, scenarios)

        return [
            ("primary order not delivered", primary_fails),
            ("demand 40% above forecast", lambda acts: self.evaluate(cand, ctx, acts, scenarios * 1.4)),
            ("demand 40% below forecast", lambda acts: self.evaluate(cand, ctx, acts, scenarios * 0.6)),
        ]

    def anomaly(self, cand: DecisionCandidate, ctx: AuthoritativeContext, params: ValidatorParams) -> dict[str, Any]:
        coh = np.asarray(cand.data_snapshot.state.get("on_hand_by_age", []), dtype=float)
        mu = cand.entity.typical_daily_volume
        carry = float(coh[1:].sum()) if len(coh) > 1 else float(coh.sum())
        so = float(ctx.signals.get("stockout_hours_yesterday", 0.0))
        jump = float(ctx.signals.get("record_jump_ratio", 0.0))
        reasons = []
        if so >= params.anomaly_min_stockout_hours and carry >= params.anomaly_min_carryover_days * mu:
            reasons.append(
                f"shelf was out of stock for {so:.0f} h yesterday, yet the record shows {carry:,.1f} units carried over"
            )
        if jump > params.anomaly_jump_ratio:
            reasons.append(f"recorded on-hand moved {jump:.1f} days of demand more than receipts and sales explain")
        return {"flag": bool(reasons), "reasons": reasons, "input": "on-hand inventory", "carryover": carry,
                "stockout_hours_yesterday": so, "record_jump_ratio": jump}

    def state_hypotheses(
        self, cand: DecisionCandidate, params: ValidatorParams, anomalous: bool
    ) -> list[tuple[str, float, dict[str, Any]]]:
        coh = np.asarray(cand.data_snapshot.state["on_hand_by_age"], dtype=float)
        mults = list(params.error_multipliers)
        p1 = params.prior_anomalous if anomalous else params.prior_clean
        others = (1 - p1) / (len(mults) - 1)
        out = []
        for m in mults:
            true = coh.copy()
            true[1:] = coh[1:] * m  # today's receipts are verified; carried-over stock is uncertain
            label = "record correct" if m == 1.0 else f"carried-over stock is {int(round(100 * m))}% of record"
            out.append((label, p1 if m == 1.0 else others, {"on_hand_by_age": true}))
        return out
