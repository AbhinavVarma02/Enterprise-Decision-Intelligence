"""Independent decision validation engine.

The engine receives a `DecisionCandidate` and an `AuthoritativeContext` and never sees the policy that
produced the candidate. Domain knowledge comes from a `DomainAdapter` (cost evaluation, scenario
sampling, candidate grid, stress cases, state hypotheses). The gates and outcome rules are generic.

Outcome precedence (first match wins; there is no blended score):
  1. reject       a hard constraint fails (G2) or the claimed financials are inconsistent (G3 fail)
  2. defer        data is stale or critical evidence is missing (G1/G6 fail) and waiting is cheap
     escalate     same, but waiting is expensive
  3. investigate  an input looks wrong (G1 warn) and the value of verifying it exceeds its cost
  4. escalate     downside risk (G4) or stress fragility (G5) fails
  5. escalate     governance requires approval (G7)
  6. recommend    otherwise
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from edi.information_value.voi import evpi
from edi.simulation.engine import cvar
from edi.validation.schema import (
    AuthoritativeContext,
    DecisionCandidate,
    GateResult,
    GateStatus,
    ValidationReport,
)

TOL = 1e-6


@dataclass(frozen=True)
class ValidatorParams:
    financial_tol_warn: float = 0.05
    financial_tol_fail: float = 0.15
    cvar_alpha: float = 0.9
    loss_tolerance_mult: float = 1.6
    stress_tolerance_mult: float = 2.5
    hedge_cost_share: float = (
        0.10  # an alternative counts as a cheap hedge within this share of daily revenue
    )
    uncertainty_ratio_warn: float = 1.5
    defer_cost_share: float = 0.25
    anomaly_min_stockout_hours: float = 4
    anomaly_min_carryover_days: float = 0.25
    anomaly_jump_ratio: float = 0.5
    prior_clean: float = 0.95
    prior_anomalous: float = 0.35
    verification_cost_multiplier: float = 1.0
    error_multipliers: tuple[float, ...] = (1.0, 0.7, 0.45, 0.2, 0.0)
    n_scenarios: int = 100
    rho: float = 0.5
    seed: int = 20261125

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> ValidatorParams:
        v = cfg["validation"]
        return cls(
            financial_tol_warn=v["financial_tol_warn"],
            financial_tol_fail=v["financial_tol_fail"],
            cvar_alpha=v["cvar_alpha"],
            loss_tolerance_mult=v["loss_tolerance_mult"],
            stress_tolerance_mult=v["stress_tolerance_mult"],
            uncertainty_ratio_warn=v["uncertainty_ratio_warn"],
            anomaly_min_stockout_hours=v["anomaly_min_stockout_hours"],
            anomaly_min_carryover_days=v["anomaly_min_cover_days"],
            prior_clean=v["prior_clean"],
            prior_anomalous=v["prior_anomalous"],
            error_multipliers=tuple(v["error_multipliers"]),
            n_scenarios=int(cfg["benchmark"]["scenarios"]),
            rho=float(cfg["benchmark"]["scenario_day_correlation"]),
            seed=int(cfg["benchmark"]["seed"]),
        )


class DomainAdapter(Protocol):
    name: str

    def revenue_scale(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> float: ...

    def scenarios(
        self, cand: DecisionCandidate, k: int, rho: float, rng: np.random.Generator
    ) -> np.ndarray: ...

    def evaluate(
        self,
        cand: DecisionCandidate,
        ctx: AuthoritativeContext,
        actions: np.ndarray,
        scenarios: np.ndarray,
        state: dict[str, Any] | None = None,
        terms: str = "authoritative",
    ) -> np.ndarray: ...

    def grid(self, cand: DecisionCandidate, ctx: AuthoritativeContext) -> np.ndarray: ...

    def stress_cases(
        self, cand: DecisionCandidate, ctx: AuthoritativeContext, scenarios: np.ndarray
    ) -> list[tuple[str, Any]]: ...

    def anomaly(
        self, cand: DecisionCandidate, ctx: AuthoritativeContext, params: ValidatorParams
    ) -> dict[str, Any]: ...

    def state_hypotheses(
        self, cand: DecisionCandidate, params: ValidatorParams, anomalous: bool
    ) -> list[tuple[str, float, dict[str, Any]]]: ...

    def required_state(self) -> list[str]: ...


def _rng(params: ValidatorParams, decision_id: str) -> np.random.Generator:
    h = hashlib.sha256(f"validator|{params.seed}|{decision_id}".encode()).digest()
    return np.random.default_rng(int.from_bytes(h[:8], "little"))


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def _usd(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def validate(
    cand: DecisionCandidate,
    ctx: AuthoritativeContext,
    adapter: DomainAdapter,
    params: ValidatorParams,
    scenarios: np.ndarray | None = None,
) -> ValidationReport:
    """Validate a candidate. `scenarios` may be supplied (e.g. the browser parity fixtures); otherwise the
    validator samples its own from the candidate's forecast with a decision-keyed seed."""
    gates: list[GateResult] = []
    reasons: list[str] = []
    metrics: dict[str, float | None] = {}
    names = [r.name for r in cand.constraints.resources]
    auth = {r.name: r for r in ctx.constraints.resources}
    a = np.array(cand.action_vector(), dtype=float)
    rev = adapter.revenue_scale(cand, ctx)
    metrics["revenue_scale"] = rev

    # ---- G6 missing critical evidence
    missing = []
    if cand.forecast is None:
        missing.append("forecast distribution")
    for key in adapter.required_state():
        if key not in cand.data_snapshot.state:
            missing.append(f"state '{key}'")
    unknown_auth = [n for n in names if n not in auth]
    if unknown_auth:
        missing.append(f"authoritative terms for {unknown_auth}")
    g6 = GateResult(
        gate="G6",
        name="Missing critical evidence",
        status="fail" if missing else "pass",
        summary=("Missing: " + ", ".join(missing)) if missing else "Required evidence present.",
        evidence={"missing": missing},
    )

    # ---- G1 data integrity and freshness
    snap = cand.data_snapshot
    stale = snap.age_hours > ctx.freshness_max_age_hours
    hist_gap = snap.history_days_missing > 1
    anom: dict[str, Any] = (
        adapter.anomaly(cand, ctx, params) if not missing else {"flag": False, "reasons": []}
    )
    g1_status: GateStatus = "fail" if (stale or hist_gap) else ("warn" if anom["flag"] else "pass")
    parts = []
    if stale:
        parts.append(f"snapshot is {snap.age_hours:.0f} h old (limit {ctx.freshness_max_age_hours:.0f} h)")
    if hist_gap:
        parts.append(f"{snap.history_days_missing} days of sales history missing")
    parts += anom.get("reasons", [])
    g1 = GateResult(
        gate="G1",
        name="Data integrity and freshness",
        status=g1_status,
        summary="; ".join(parts) if parts else "Snapshot is current and internally consistent.",
        evidence={"age_hours": snap.age_hours, "history_days_missing": snap.history_days_missing, **anom},
    )

    # ---- G2 constraint satisfaction against authoritative terms
    viol: list[str] = []
    warn2: list[str] = []
    for i, nm in enumerate(names):
        q = a[i]
        r = auth.get(nm)
        if r is None:
            continue
        if q < -TOL:
            viol.append(f"{nm} quantity is negative")
        if q > TOL and not (r.eligible and r.available):
            viol.append(f"{nm} supplier is not {'qualified' if not r.eligible else 'available'}")
        if q > r.capacity * (1 + 1e-6) + TOL:
            viol.append(f"{nm} order of {_fmt(q)} units exceeds current capacity of {_fmt(r.capacity)}")
        if TOL < q < r.min_quantity - TOL:
            viol.append(f"{nm} order of {_fmt(q)} units is below the minimum of {_fmt(r.min_quantity)}")
        cr = cand.constraints.resources[i]
        if cr.lead_days != r.lead_days:
            warn2.append(f"{nm}: plan assumed lead {cr.lead_days} d, current terms say {r.lead_days} d")
        if abs(cr.unit_cost - r.unit_cost) > 1e-6 * max(1.0, r.unit_cost):
            warn2.append(f"{nm}: plan priced at {_usd(cr.unit_cost)}, current price {_usd(r.unit_cost)}")
    auth_costs = np.array(
        [
            auth[n].unit_cost if n in auth else cand.constraints.resources[i].unit_cost
            for i, n in enumerate(names)
        ]
    )
    # Only committed resources count toward spend (usage-priced limits, e.g. on-demand caps, do not).
    committed = np.array(
        [
            bool((auth[n] if n in auth else cand.constraints.resources[i]).attributes.get("committed", True))
            for i, n in enumerate(names)
        ]
    )
    spend = float((a * committed) @ auth_costs)
    if spend > ctx.constraints.budget * (1 + 1e-6) + TOL:
        viol.append(f"spend of {_usd(spend)} exceeds the budget of {_usd(ctx.constraints.budget)}")
    if ctx.constraints.min_commitment > 0 and a[0] + TOL < ctx.constraints.min_commitment:
        viol.append(
            f"{names[0]} order is below the contractual minimum of {_fmt(ctx.constraints.min_commitment)}"
        )
    metrics["spend"] = spend
    g2 = GateResult(
        gate="G2",
        name="Constraint satisfaction",
        status="fail" if viol else ("warn" if warn2 else "pass"),
        summary="; ".join(viol or warn2) or "All hard constraints hold under current terms.",
        evidence={"violations": viol, "warnings": warn2, "spend": spend, "budget": ctx.constraints.budget},
    )

    # ---- scenario-based gates
    g3 = g4 = g5 = None
    best_action = None
    voi_info: dict[str, Any] | None = None
    can_eval = cand.forecast is not None and not missing
    if can_eval:
        S = (
            scenarios
            if scenarios is not None
            else adapter.scenarios(cand, params.n_scenarios, params.rho, _rng(params, cand.decision_id))
        )
        grid = adapter.grid(cand, ctx)
        C_grid = adapter.evaluate(cand, ctx, grid, S)
        C_c = adapter.evaluate(cand, ctx, a[None, :], S)[0]
        e_c, cv_c = float(C_c.mean()), float(cvar(C_c, params.cvar_alpha))
        e_g, cv_g = C_grid.mean(axis=1), cvar(C_grid, params.cvar_alpha)
        ib = int(np.argmin(e_g))
        best_action = {nm: float(grid[ib, i]) for i, nm in enumerate(names)}
        metrics.update(
            expected_cost=e_c,
            cvar=cv_c,
            best_grid_expected_cost=float(e_g[ib]),
            prob_loss_over_tolerance=float(np.mean(C_c > e_c + rev)),
        )

        # G3 financial consistency. Two separate questions:
        #   (a) does the claimed expected cost match the candidate's own stated terms? Sampling error
        #       and the optimizer's in-sample bias are tolerated through a standard-error allowance;
        #   (b) how much do the candidate's price and lead-time assumptions differ in cost from the
        #       authoritative terms? Measured on common scenarios, so no sampling noise.
        C_own = adapter.evaluate(cand, ctx, a[None, :], S, terms="candidate")[0]
        e_own = float(C_own.mean())
        impact = e_c - e_own
        scale3 = max(abs(e_c), 0.25 * rev, 1e-9)
        impact_rel = abs(impact) / scale3
        claimed = cand.scenario_results.expected_cost if cand.scenario_results else None
        k_claim = cand.scenario_results.n_scenarios if cand.scenario_results else 0
        se = float(C_own.std(ddof=1) * np.sqrt(1.0 / len(C_own) + (1.0 / k_claim if k_claim else 1.0)))
        claim_gap = None if claimed is None else abs(claimed - e_own)
        claim_tol_fail = max(params.financial_tol_fail * scale3, 4.0 * se)
        claim_tol_warn = max(params.financial_tol_warn * scale3, 2.0 * se)
        st3 = "pass"
        notes3 = []
        if impact_rel > params.financial_tol_fail:
            st3 = "fail"
            notes3.append(
                f"plan terms understate cost by {_usd(impact)} versus current terms"
                if impact > 0
                else f"plan terms overstate cost by {_usd(-impact)} versus current terms"
            )
        elif impact_rel > params.financial_tol_warn:
            st3 = "warn"
            notes3.append(f"plan terms differ from current terms by {_usd(impact)}")
        if claim_gap is None:
            st3 = "warn" if st3 == "pass" else st3
            notes3.append(f"no claimed cost to reconcile; independent estimate {_usd(e_c)}")
        elif claim_gap > claim_tol_fail:
            st3 = "fail"
            notes3.append(
                f"claimed expected cost {_usd(claimed or 0)} does not reconcile with {_usd(e_own)} "
                f"recomputed on its own terms (tolerance {_usd(claim_tol_fail)})"
            )
        elif claim_gap > claim_tol_warn and st3 == "pass":
            st3 = "warn"
            notes3.append(f"claimed {_usd(claimed or 0)} vs recomputed {_usd(e_own)}")
        g3 = GateResult(
            gate="G3",
            name="Financial consistency",
            status=st3,  # type: ignore[arg-type]
            summary="; ".join(notes3)
            if notes3
            else (
                f"Claimed {_usd(claimed or 0)} reconciles with {_usd(e_own)} recomputed; current terms change cost by {_usd(impact)}."
            ),
            evidence={
                "claimed": claimed,
                "recomputed_own_terms": e_own,
                "recomputed_current_terms": e_c,
                "assumption_impact": impact,
                "assumption_impact_relative": impact_rel,
                "claim_gap": claim_gap,
                "claim_tolerance": claim_tol_fail,
                "standard_error": se,
            },
        )
        metrics["financial_relative_difference"] = impact_rel
        metrics["claim_gap"] = claim_gap

        # G4 downside risk: is there a cheap hedge with a much better tail?
        hedge = e_g <= e_c + params.hedge_cost_share * rev
        tail_gain = float(cv_c - cv_g[hedge].min()) if hedge.any() else 0.0
        tol4 = params.loss_tolerance_mult * 0.25 * rev
        fc = cand.forecast
        assert fc is not None
        qarr = np.array(fc.quantiles)
        lv = fc.levels
        unc = None
        if 0.1 in lv and 0.9 in lv and 0.5 in lv:
            med = np.maximum(qarr[:, lv.index(0.5)], 1e-9)
            unc = float(np.mean((qarr[:, lv.index(0.9)] - qarr[:, lv.index(0.1)]) / med))
        st4: GateStatus = (
            "fail"
            if tail_gain > tol4
            else ("warn" if tail_gain > tol4 / 2 or (unc or 0) > params.uncertainty_ratio_warn else "pass")
        )
        ih = int(np.argmin(np.where(hedge, cv_g, np.inf))) if hedge.any() else ib
        g4 = GateResult(
            gate="G4",
            name="Uncertainty and downside risk",
            status=st4,
            summary=(
                f"Expected {_usd(e_c)}; worst-{100 - int(round(params.cvar_alpha * 100))}% average {_usd(cv_c)}. "
                + (
                    f"A hedge within {_usd(params.hedge_cost_share * rev)} of expected cost lowers it by "
                    f"{_usd(tail_gain)} (tolerance {_usd(tol4)})."
                    if tail_gain > 1e-9
                    else "No cheaper-tail alternative found."
                )
            ),
            evidence={
                "expected_cost": e_c,
                "cvar": cv_c,
                "tail_gain": tail_gain,
                "tolerance": tol4,
                "uncertainty_ratio": unc,
                "hedge_action": {nm: float(grid[ih, i]) for i, nm in enumerate(names)},
            },
        )
        metrics["tail_gain"] = tail_gain

        # G5 stress resilience: worst stress cost vs the most robust cheap hedge
        worst_c, worst_g, details = -np.inf, np.full(len(grid), -np.inf), {}
        for label, fn in adapter.stress_cases(cand, ctx, S):
            sc_c = float(fn(a[None, :]).mean())
            sc_g = fn(grid).mean(axis=1)
            details[label] = {"candidate": sc_c, "best": float(sc_g.min())}
            worst_c = max(worst_c, sc_c)
            worst_g = np.maximum(worst_g, sc_g)
        if np.isfinite(worst_c):
            robust_gain = float(worst_c - worst_g[hedge].min()) if hedge.any() else 0.0
            tol5 = params.stress_tolerance_mult * 0.25 * rev
            st5: GateStatus = "fail" if robust_gain > tol5 else ("warn" if robust_gain > tol5 / 2 else "pass")
            g5 = GateResult(
                gate="G5",
                name="Stress-case resilience",
                status=st5,
                summary=(
                    f"Worst stress-case cost {_usd(worst_c)}; a cheap hedge would cap it "
                    f"{_usd(robust_gain)} lower (tolerance {_usd(tol5)})."
                ),
                evidence={"cases": details, "robust_gain": robust_gain, "tolerance": tol5},
            )
            metrics["stress_gain"] = robust_gain

        # Value of information when an input looks wrong. EVPI (textbook) compares perfect information
        # with the best hedged action under the prior. The validator's real alternative to verifying is
        # executing the candidate, so it also reports the value of verification relative to the
        # candidate, E_prior[C(candidate)] - V1, and investigates when that exceeds the cost.
        if anom["flag"]:
            hyps = adapter.state_hypotheses(cand, params, anomalous=True)
            probs = np.array([p for _, p, _ in hyps])
            costs = np.column_stack(
                [adapter.evaluate(cand, ctx, grid, S, state=st).mean(axis=1) for _, _, st in hyps]
            )
            cand_by_state = np.array(
                [float(adapter.evaluate(cand, ctx, a[None, :], S, state=st).mean()) for _, _, st in hyps]
            )
            res = evpi(costs, probs, [lbl for lbl, _, _ in hyps])
            value_vs_candidate = max(0.0, float(probs @ cand_by_state) - res.perfect_information_cost)
            voi_info = res.to_dict() | {
                "value_vs_candidate": value_vs_candidate,
                "candidate_expected_cost_under_prior": float(probs @ cand_by_state),
                "investigation_cost": ctx.investigation_cost,
                "worth_investigating": bool(
                    value_vs_candidate > params.verification_cost_multiplier * ctx.investigation_cost
                ),
                "input": anom.get("input", "state"),
            }
            metrics["evpi"] = res.evpi
            metrics["value_vs_candidate"] = value_vs_candidate
    else:
        for gid, nm in (
            ("G3", "Financial consistency"),
            ("G4", "Uncertainty and downside risk"),
            ("G5", "Stress-case resilience"),
        ):
            placeholder = GateResult(
                gate=gid, name=nm, status="warn", summary="Not evaluated: no usable forecast."
            )
            if gid == "G3":
                g3 = placeholder
            elif gid == "G4":
                g4 = placeholder
            else:
                g5 = placeholder

    # ---- G7 governance
    gov: list[str] = []
    if spend > ctx.approval_threshold + TOL:
        gov.append(
            f"spend of {_usd(spend)} is above the approval threshold of {_usd(ctx.approval_threshold)}"
        )
    total_q = float(a[committed].sum()) if committed.any() else float(a.sum())
    usable = {
        n: (auth[n].eligible and auth[n].available and auth[n].capacity > TOL) for n in names if n in auth
    }
    for nm, share in ctx.max_share.items():
        others_usable = any(v for k, v in usable.items() if k != nm)
        if nm in names and total_q > TOL and others_usable:
            s = a[names.index(nm)] / total_q
            if s > share + 1e-9:
                gov.append(
                    f"{nm} share {100 * s:.0f}% exceeds policy {100 * share:.0f}% while standard supply is available"
                )
    g7 = GateResult(
        gate="G7",
        name="Governance and approval",
        status="warn" if gov else "pass",
        summary=("Approval required: " + "; ".join(gov)) if gov else "Within delegated authority.",
        evidence={"approval_required": bool(gov), "reasons": gov},
    )

    gates = [g1, g2, g3, g4, g5, g6, g7]  # type: ignore[list-item]
    gates = [g for g in gates if g is not None]
    by = {g.gate: g for g in gates}

    # ---- outcome
    outcome = "recommend"
    recommended = None
    if by["G2"].status == "fail" or by["G3"].status == "fail":
        outcome = "reject"
        reasons.append(by["G2"].summary if by["G2"].status == "fail" else by["G3"].summary)
        recommended = best_action
    elif by["G1"].status == "fail" or by["G6"].status == "fail":
        wait_cost = None
        if can_eval:
            zero = np.zeros((1, len(names)))
            best = float(metrics["best_grid_expected_cost"] or 0.0)
            wait_cost = float(adapter.evaluate(cand, ctx, zero, S).mean()) - best
            metrics["cost_of_waiting"] = wait_cost
        if wait_cost is not None and wait_cost <= params.defer_cost_share * rev:
            outcome = "defer"
            lead_reason = by["G1"].summary if by["G1"].status == "fail" else by["G6"].summary
            reasons.append(f"{lead_reason.rstrip('.')}. Waiting a day costs about {_usd(wait_cost)}.")
        else:
            outcome = "escalate"
            reasons.append(
                (by["G1"].summary if by["G1"].status == "fail" else by["G6"].summary).rstrip(".")
                + ". Waiting is expensive or cannot be priced, so a planner must decide."
            )
    elif voi_info is not None and voi_info["worth_investigating"]:
        outcome = "investigate"
        reasons.append(
            f"{by['G1'].summary.rstrip('.')}. Verifying it is worth about {_usd(voi_info['value_vs_candidate'])} against a cost of "
            f"{_usd(ctx.investigation_cost)}."
        )
    elif by["G4"].status == "fail" or by["G5"].status == "fail":
        outcome = "escalate"
        reasons.append(by["G4"].summary if by["G4"].status == "fail" else by["G5"].summary)
        hedge_act = by["G4"].evidence.get("hedge_action")
        recommended = hedge_act if isinstance(hedge_act, dict) else best_action
    elif by["G7"].status == "warn":
        outcome = "escalate"
        reasons.append(by["G7"].summary)
    else:
        reasons.append("All gates passed or raised only warnings that do not change the action.")

    report = ValidationReport(
        decision_id=cand.decision_id,
        outcome=outcome,  # type: ignore[arg-type]
        reasons=reasons,
        gates=gates,
        recommended_action=recommended,
        metrics={k: (float(v) if v is not None else None) for k, v in metrics.items()},
        value_of_information=voi_info,
    )
    from edi.explain.templates import explain

    report.explanation = explain(cand, report)
    return report
