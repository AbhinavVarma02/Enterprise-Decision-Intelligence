/**
 * Perishable inventory evaluator. Port of edi.simulation.engine (Python). The operation order matches
 * the Python reference so results agree to floating-point tolerance (see engine.test.ts).
 */
import type { Econ } from "./types";

export const MAX_HORIZON = 4;
export const shortageCost = (e: Econ): number => e.price + e.goodwill;
export const terminalCharge = (e: Econ): number =>
  e.terminal_waste_risk * (e.unit_cost + e.disposal) + e.holding - e.unit_cost;

export interface HorizonResult {
  cost: Float64Array[]; // [action][scenario]
  shortage: Float64Array[];
  waste: Float64Array[];
  endUnits: Float64Array[];
  procurement: number[];
}

export function evaluateActions(
  cohorts: readonly number[],
  pipeline: readonly number[],
  orders: readonly (readonly number[])[],
  leads: readonly number[],
  unitCosts: readonly number[],
  demand: readonly (readonly number[])[],
  econ: Econ,
): HorizonResult {
  const A = orders.length;
  const K = demand.length;
  const H = K ? demand[0].length : 0;
  const L = econ.shelf_life;
  if (cohorts.length !== L) throw new Error(`cohorts length ${cohorts.length} != shelf life ${L}`);
  const sc = shortageCost(econ);
  const tc = terminalCharge(econ);
  const inv = new Float64Array(L);
  const out: HorizonResult = { cost: [], shortage: [], waste: [], endUnits: [], procurement: [] };
  for (let a = 0; a < A; a++) {
    const q = orders[a];
    const proc = q[0] * unitCosts[0] + q[1] * unitCosts[1] + q[2] * unitCosts[2];
    const cost = new Float64Array(K);
    const short = new Float64Array(K);
    const waste = new Float64Array(K);
    const ends = new Float64Array(K);
    for (let k = 0; k < K; k++) {
      for (let i = 0; i < L; i++) inv[i] = cohorts[i];
      let c = 0;
      let sh = 0;
      let ws = 0;
      let end = 0;
      for (let t = 0; t < H; t++) {
        let arr = t < pipeline.length ? pipeline[t] : 0;
        for (let s = 0; s < 3; s++) if (leads[s] === t) arr = arr + q[s];
        inv[0] += arr;
        let remaining = demand[k][t];
        for (let i = L - 1; i >= 0; i--) {
          const take = Math.min(inv[i], remaining);
          inv[i] -= take;
          remaining -= take;
        }
        const w = inv[L - 1];
        inv[L - 1] = 0;
        end = 0;
        for (let i = 0; i < L; i++) end += inv[i];
        for (let i = L - 1; i >= 1; i--) inv[i] = inv[i - 1];
        inv[0] = 0;
        c += econ.holding * end + econ.disposal * w + sc * remaining;
        sh += remaining;
        ws += w;
      }
      c += tc * end + proc;
      cost[k] = c;
      short[k] = sh;
      waste[k] = ws;
      ends[k] = end;
    }
    out.cost.push(cost);
    out.shortage.push(short);
    out.waste.push(waste);
    out.endUnits.push(ends);
    out.procurement.push(proc);
  }
  return out;
}

export function mean(xs: ArrayLike<number>): number {
  let s = 0;
  for (let i = 0; i < xs.length; i++) s += xs[i];
  return xs.length ? s / xs.length : NaN;
}

/** Mean of the worst (1 - alpha) share of equally weighted outcomes (Rockafellar-Uryasev). */
export function cvar(xs: ArrayLike<number>, alpha: number): number {
  const c = Array.from(xs).sort((x, y) => x - y);
  const n = c.length;
  const k = (1 - alpha) * n;
  const full = Math.floor(k);
  const frac = k - full;
  let tail = 0;
  for (let i = 0; i < full; i++) tail += c[n - 1 - i];
  if (frac > 1e-12 && full < n) tail += frac * c[n - 1 - full];
  return tail / k;
}

export function std(xs: ArrayLike<number>, ddof = 1): number {
  const m = mean(xs);
  let s = 0;
  for (let i = 0; i < xs.length; i++) s += (xs[i] - m) ** 2;
  return Math.sqrt(s / (xs.length - ddof));
}

export function argmin(xs: ArrayLike<number>): number {
  let best = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i] < xs[best]) best = i;
  return best;
}

export function horizonFor(leads: readonly number[], capacities: readonly number[]): number {
  let lead = 0;
  let any = false;
  for (let i = 0; i < leads.length; i++) {
    if (capacities[i] > 0) {
      lead = any ? Math.max(lead, leads[i]) : leads[i];
      any = true;
    }
  }
  return Math.min(MAX_HORIZON, Math.max(2, lead + 1));
}

/** Piecewise-linear inverse CDF through quantile knots with linear tails (same rule as Python). */
export function quantileFunction(q: readonly number[], levels: readonly number[], u: number): number {
  const qq = q.slice();
  for (let i = 1; i < qq.length; i++) qq[i] = Math.max(qq[i], qq[i - 1]);
  const q0 = Math.max(0, 2 * qq[0] - qq[1]);
  const q1 = Math.max(qq[qq.length - 1], 2 * qq[qq.length - 1] - qq[qq.length - 2]);
  const xs = [0, ...levels, 1];
  const ys = [Math.min(q0, qq[0]), ...qq, q1];
  if (u <= 0) return Math.max(ys[0], 0);
  if (u >= 1) return Math.max(ys[ys.length - 1], 0);
  let j = 0;
  while (j < xs.length - 2 && u >= xs[j + 1]) j++;
  const v = ys[j] + ((ys[j + 1] - ys[j]) * (u - xs[j])) / (xs[j + 1] - xs[j]);
  return Math.max(v, 0);
}
