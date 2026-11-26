/** Bounded candidate-action grid. Port of edi.optimization.milp.action_grid. */
import type { Resource, Supply, Terms } from "./types";

export function linspace(start: number, stop: number, num: number): number[] {
  if (num <= 1) return [start];
  const step = (stop - start) / (num - 1);
  const out = new Array<number>(num);
  for (let i = 0; i < num; i++) out[i] = i * step + start;
  out[num - 1] = stop;
  return out;
}

const NAMES = ["primary", "alternate", "expedite"] as const;

export function supplyFromTerms(terms: Terms, approvalThreshold = Infinity, maxExpediteShare = 1): Supply {
  const by = new Map(terms.resources.map((r) => [r.name, r]));
  const rs: Resource[] = NAMES.map((n) => {
    const r = by.get(n);
    if (!r) throw new Error(`missing resource ${n}`);
    return { ...r, attributes: { ...r.attributes } };
  });
  return {
    leads: rs.map((r) => r.lead_days),
    unitCosts: rs.map((r) => r.unit_cost),
    capacities: rs.map((r) => (r.eligible && r.available ? r.capacity : 0)),
    moqs: rs.map((r) => r.min_quantity),
    budget: terms.budget,
    minCommitment: terms.min_commitment ?? 0,
    approvalThreshold,
    maxExpediteShare,
    resources: rs,
  };
}

export function termsFromSupply(s: Supply): Terms {
  return {
    resources: s.resources.map((r, i) => ({ ...r, lead_days: s.leads[i], unit_cost: s.unitCosts[i] })),
    budget: s.budget,
    min_commitment: s.minCommitment,
  };
}

function uniqueSorted(xs: number[]): number[] {
  const s = xs.slice().sort((a, b) => a - b);
  const out: number[] = [];
  for (const x of s) if (out.length === 0 || out[out.length - 1] !== x) out.push(x);
  return out;
}

export function actionGrid(s: Supply, horizon: number, nPrimary = 12, nAlt = 6, nExp = 5): number[][] {
  const caps = s.capacities.map((c, i) => (s.leads[i] >= horizon ? 0 : c));
  const [pri, alt, exp] = [nPrimary, nAlt, nExp].map((count, i) => caps[i] > 0 && caps[i] >= s.moqs[i]
    ? uniqueSorted([0, ...linspace(s.moqs[i], caps[i], count)]) : [0]);
  const out: number[][] = [];
  for (const p of pri)
    for (const a of alt)
      for (const e of exp) {
        const spend = p * s.unitCosts[0] + a * s.unitCosts[1] + e * s.unitCosts[2];
        if (spend > s.budget + 1e-9) continue;
        if (s.minCommitment > 0 && p < s.minCommitment - 1e-9) continue;
        out.push([p, a, e]);
      }
  return out;
}

export function orderIsFeasible(orders: number[], supply: Supply): boolean {
  return orders.every((q, i) => q >= 0 && q <= supply.capacities[i] + 1e-6 && (q <= 1e-6 || q >= supply.moqs[i] - 1e-6))
    && orders[0] >= supply.minCommitment - 1e-6
    && orders.reduce((spend, q, i) => spend + q * supply.unitCosts[i], 0) <= supply.budget + 1e-6;
}
