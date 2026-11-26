/**
 * Scenario Studio calculation: bounded grid search over the candidate-action space under user
 * assumptions, validation of the recommended action and cost-of-inaction comparison.
 * Port of edi.export.web.studio_evaluate (parity-tested on golden fixtures).
 */
import { actionGrid, supplyFromTerms, termsFromSupply } from "./grid";
import { argmin, cvar, evaluateActions, horizonFor, mean } from "./evaluator";
import { alternatives } from "./inaction";
import { validateCandidate } from "./validator";
import type { DecisionCase, StudioMods, StudioResult, Supply, ValidatorParams } from "./types";

export const STUDIO_LIMITS = {
  demand_shift: [-0.5, 0.8],
  primary_delay_days: [0, 2],
  cost_change: [-0.3, 0.6],
  budget_mult: [0.2, 2],
  risk_weight: [0, 0.95],
} as const;

export function modifiedSupply(c: DecisionCase, mods: StudioMods): Supply {
  const s = supplyFromTerms(c.current_terms, c.approval_threshold, c.max_expedite_share);
  const sup: Supply = { ...s, leads: s.leads.slice(), unitCosts: s.unitCosts.slice(), resources: s.resources.map((r) => ({ ...r })) };
  sup.budget = c.current_terms.budget * (mods.budget_mult ?? 1);
  const delay = mods.primary_delay_days ?? 0;
  if (delay) {
    sup.leads[0] += delay;
    sup.resources[0].lead_days = sup.leads[0];
  }
  const cc = mods.cost_change ?? 0;
  if (cc) {
    sup.unitCosts = sup.unitCosts.map((x) => x * (1 + cc));
    sup.resources.forEach((r, i) => (r.unit_cost = sup.unitCosts[i]));
  }
  if (mods.primary_available === false) sup.resources[0].available = false;
  if (mods.alternate_eligible === false) sup.resources[1].eligible = false;
  if (mods.expedite_available === false) sup.resources[2].available = false;
  sup.capacities = sup.resources.map((r) => (r.eligible && r.available ? r.capacity : 0));
  return sup;
}

export function studioEvaluate(c: DecisionCase, mods: StudioMods, params: ValidatorParams): StudioResult {
  const econ = c.economics;
  const sup = modifiedSupply(c, mods);
  const cohorts = mods.use_verified ? c.state.verified_on_hand_by_age : c.state.recorded_on_hand_by_age;
  const pipeline = c.state.pipeline_by_day;
  const shift = 1 + (mods.demand_shift ?? 0);
  const h = Math.min(3, horizonFor(sup.leads, sup.capacities));
  const S = c.scenarios.map((row) => row.slice(0, h).map((x) => x * shift));
  const lam = mods.risk_weight ?? 0.5;
  const alpha = mods.alpha ?? 0.9;
  const grid = actionGrid(sup, h);
  const pipe = new Array(h).fill(0);
  for (let i = 0; i < Math.min(h, pipeline.length); i++) pipe[i] = pipeline[i];
  const C = evaluateActions(cohorts, pipe, grid, sup.leads, sup.unitCosts, S, econ).cost;
  const E = C.map((x) => mean(x));
  const CV = C.map((x) => cvar(x, alpha));
  const score = E.map((e, i) => (1 - lam) * e + lam * CV[i]);
  const ib = argmin(E);
  const ir = argmin(score);
  const orig = c.candidate.orders.map((q, i) => Math.min(q, sup.capacities[i]));
  const Co = evaluateActions(cohorts, pipe, [orig], sup.leads, sup.unitCosts, S, econ).cost[0];
  const rec = grid[ir];
  const terms = termsFromSupply(sup);
  const fq = c.forecast.quantiles.slice(0, h).map((row) => row.map((x) => Math.max(0, x * shift)));
  const validation = validateCandidate(
    {
      decision_id: `studio.${c.id}`,
      typical_daily_volume: c.mu,
      age_hours: 24,
      history_days_missing: 0,
      on_hand_by_age: cohorts,
      pipeline_by_day: pipeline,
      action: { primary: rec[0], alternate: rec[1], expedite: rec[2] },
      plan_terms: terms,
      plan_econ: econ,
      forecast: { levels: c.forecast.levels, quantiles: fq },
      claimed_expected_cost: E[ir],
      claimed_n_scenarios: S.length,
      cvar_alpha: alpha,
    },
    {
      terms,
      econ,
      approval_threshold: sup.approvalThreshold,
      max_share: { expedite: sup.maxExpediteShare },
      freshness_max_age_hours: c.freshness_max_age_hours,
      signals: mods.use_verified ? {} : c.signals,
      investigation_cost: c.investigation_cost,
      review_cost: c.review_cost,
    },
    params,
    S,
  );
  const alts = alternatives(rec, cohorts, pipeline, sup, econ, S, c.review_cost, alpha, c.revenue_scale);
  const pri = [...new Set(grid.map((g) => g[0]))].sort((x, y) => x - y);
  const alt = [...new Set(grid.map((g) => g[1]))].sort((x, y) => x - y);
  const surf: (number | null)[][] = pri.map(() => alt.map(() => null));
  grid.forEach((g, k) => {
    if (Math.abs(g[2] - rec[2]) <= 1e-8 + 1e-5 * Math.abs(rec[2])) surf[pri.indexOf(g[0])][alt.indexOf(g[1])] = score[k];
  });
  return {
    horizon: h,
    grid_size: grid.length,
    best_expected: { orders: grid[ib], expected: E[ib], cvar: CV[ib] },
    recommended: { orders: rec, expected: E[ir], cvar: CV[ir], score: score[ir] },
    original: { orders: orig, expected: mean(Co), cvar: cvar(Co, alpha), score: (1 - lam) * mean(Co) + lam * cvar(Co, alpha) },
    validation,
    alternatives: alts,
    surface: { primary: pri, alternate: alt, value: surf, measure: lam > 0 ? "risk_adjusted" : "expected" },
  };
}
