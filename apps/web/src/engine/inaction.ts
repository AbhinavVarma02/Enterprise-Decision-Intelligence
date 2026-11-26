/**
 * Cost of inaction. Port of edi.validation.inaction.alternatives: options are evaluated over the decision
 * horizon; units that waiting pushes to the horizon end or later are charged and credited as leftover stock.
 */
import { cvar, evaluateActions, mean, terminalCharge } from "./evaluator";
import type { Alternative, Econ, Supply } from "./types";

function quantile90(xs: Float64Array): number {
  // numpy default (linear) interpolation
  const s = Array.from(xs).sort((a, b) => a - b);
  const pos = 0.9 * (s.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, s.length - 1);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

export function alternatives(
  candidate: number[],
  cohorts: number[],
  pipeline: number[],
  supply: Supply,
  econ: Econ,
  scenarios: number[][],
  reviewCost: number,
  alpha = 0.9,
  toleranceMargin: number | null = null,
): Alternative[] {
  const h = scenarios[0].length;
  const pipe = new Array(h).fill(0);
  for (let i = 0; i < Math.min(h, pipeline.length); i++) pipe[i] = pipeline[i];
  const caps = supply.capacities;
  const cand = candidate.map((q, i) => Math.min(q, caps[i]));
  const smaller = cand.slice();
  smaller[0] *= 0.5;
  smaller[1] *= 0.5;
  smaller[2] = 0;
  const moq = supply.moqs[0];
  if (smaller[0] > 0 && smaller[0] < moq) smaller[0] = moq <= caps[0] ? moq : 0;
  const leads = supply.leads;
  const later = leads.map((l) => l + 1);
  const options: [string, string, number[], number[], number][] = [
    ["act_now", "Act now", cand, leads, 0],
    ["smaller", "Smaller reversible order", smaller, leads, 0],
    ["wait", "Wait one day, then order", cand, later, 0],
    ["escalate", "Escalate for same-day review", cand, leads, reviewCost],
    ["no_action", "No action", [0, 0, 0], leads, 0],
  ];
  const out: Alternative[] = [];
  let tolerance: number | null = null;
  const demandTot = scenarios.map((r) => r.reduce((s, x) => s + x, 0));
  const tc = terminalCharge(econ);
  for (const [key, label, q, ld, extra] of options) {
    const qIn = q.map((x, i) => (ld[i] < h ? x : 0));
    const qLate = q.map((x, i) => (ld[i] < h ? 0 : x));
    const res = evaluateActions(cohorts, pipe, [qIn], ld, supply.unitCosts, scenarios, econ);
    const lateQty = qLate[0] + qLate[1] + qLate[2];
    const late = qLate[0] * supply.unitCosts[0] + qLate[1] * supply.unitCosts[1] + qLate[2] * supply.unitCosts[2] + tc * lateQty;
    const c = Float64Array.from(res.cost[0], (x) => x + late + extra);
    if (tolerance === null && toleranceMargin !== null) tolerance = mean(c) + toleranceMargin;
    const fillParts = Array.from(res.shortage[0], (s, k) => s / Math.max(demandTot[k], 1e-9));
    const rec: Alternative = {
      key,
      label,
      orders: q.slice(),
      expected_cost: mean(c),
      cvar: cvar(c, alpha),
      p90: quantile90(c),
      expected_fill_rate: 1 - mean(fillParts),
      expected_waste_units: mean(res.waste[0]),
      governance_cost: extra,
      arrives_after_horizon: lateQty,
      delta_vs_act_now: 0,
    };
    if (tolerance !== null) {
      let n = 0;
      for (const x of c) if (x > tolerance) n++;
      rec.prob_over_tolerance = n / c.length;
    }
    rec.delta_vs_act_now = rec.expected_cost - (out.length ? out[0].expected_cost : rec.expected_cost);
    out.push(rec);
  }
  return out;
}
