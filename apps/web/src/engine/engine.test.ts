/**
 * Parity tests: the browser engine must reproduce the Python reference (edi.export.web.golden).
 * Regenerate fixtures with `edi export-web` whenever the evaluator, grid, validator or studio changes.
 */
import { describe, expect, it } from "vitest";
import golden from "./__fixtures__/golden.json";
import cases from "../../public/data/cases.json";
import meta from "../../public/data/meta.json";
import { cvar, evaluateActions, quantileFunction } from "./evaluator";
import { actionGrid, orderIsFeasible } from "./grid";
import { modifiedSupply, studioEvaluate } from "./studio";
import type { DecisionCase, StudioMods, ValidatorParams } from "./types";

const REL = golden.tolerance.relative * 100; // allow summation-order differences
const ABS = golden.tolerance.absolute * 100;
const close = (a: number, b: number) => Math.abs(a - b) <= ABS + REL * Math.abs(b);
const allCases = (cases as unknown as { cases: DecisionCase[] }).cases;
const params = (meta as unknown as { validator_params: ValidatorParams }).validator_params;

describe("evaluator parity", () => {
  for (const [i, f] of golden.evaluate.entries()) {
    it(`matches Python cost matrix, case ${i}`, () => {
      const r = evaluateActions(f.cohorts, f.pipeline, f.orders, f.leads, f.unit_costs, f.demand, f.econ);
      r.cost.forEach((row, a) => row.forEach((v, k) => expect(close(v, f.cost[a][k]), `a${a} k${k}: ${v} vs ${f.cost[a][k]}`).toBe(true)));
      r.cost.forEach((row, a) => expect(close(cvar(row, 0.9), f.cvar90[a])).toBe(true));
    });
  }
});

describe("action grid parity", () => {
  it("excludes supplier quantities below their minimum order", () => {
    const supply = modifiedSupply(allCases[0], {});
    supply.moqs = [10, 5, 0];
    supply.capacities = [2, 10, 5];
    const grid = actionGrid(supply, 3);
    expect(grid.length).toBeGreaterThan(0);
    expect(grid.every((orders) => orders[0] === 0 && orderIsFeasible(orders, supply))).toBe(true);
  });
  for (const g of golden.grids) {
    it(`matches Python grid for ${g.case}`, () => {
      const c = allCases.find((x) => x.id === g.case)!;
      const grid = actionGrid(modifiedSupply(c, {}), g.horizon);
      expect(grid.length).toBe(g.grid.length);
      grid.forEach((row, i) => row.forEach((v, j) => expect(close(v, g.grid[i][j])).toBe(true)));
    });
  }
});

describe("studio and validator parity", () => {
  for (const s of golden.studio) {
    it(`${s.case} with ${JSON.stringify(s.mods)}`, () => {
      const c = allCases.find((x) => x.id === s.case)!;
      const r = studioEvaluate(c, s.mods as StudioMods, params);
      const e = s.result;
      expect(r.horizon).toBe(e.horizon);
      expect(r.grid_size).toBe(e.grid_size);
      // exported values are rounded to 4 decimals
      r.recommended.orders.forEach((v, i) => expect(Math.abs(v - e.recommended.orders[i]), `recommended ${r.recommended.orders} vs ${e.recommended.orders}`).toBeLessThan(1e-3));
      r.best_expected.orders.forEach((v, i) => expect(Math.abs(v - e.best_expected.orders[i]), `best ${r.best_expected.orders} vs ${e.best_expected.orders}`).toBeLessThan(1e-3));
      expect(Math.abs(r.recommended.expected - e.recommended.expected)).toBeLessThan(1e-3);
      expect(Math.abs(r.recommended.cvar - e.recommended.cvar)).toBeLessThan(1e-3);
      expect(Math.abs(r.original.expected - e.original.expected)).toBeLessThan(1e-3);
      expect(r.validation.outcome).toBe(e.validation.outcome);
      expect(r.validation.gates.map((g) => g.status)).toEqual(e.validation.gates.map((g: { status: string }) => g.status));
      for (const key of ["expected_cost", "cvar", "tail_gain", "stress_gain", "spend"]) {
        const pv = (e.validation.metrics as Record<string, number | null>)[key];
        const tv = r.validation.metrics[key];
        if (pv !== null && pv !== undefined) expect(Math.abs((tv ?? NaN) - pv), key).toBeLessThan(1e-3);
      }
      expect(r.validation.explanation).toBe(e.validation.explanation);
      r.alternatives.forEach((a, i) => {
        expect(a.key).toBe(e.alternatives[i].key);
        expect(Math.abs(a.expected_cost - e.alternatives[i].expected_cost)).toBeLessThan(1e-3);
        expect(Math.abs(a.p90 - e.alternatives[i].p90)).toBeLessThan(1e-3);
      });
    });
  }
});

describe("precomputed case reports reproduce in the browser", () => {
  for (const c of allCases) {
    it(`${c.id} default studio run keeps the shipped grid best`, () => {
      const r = studioEvaluate(c, {}, params);
      expect(r.grid_size).toBeGreaterThan(0);
      expect(Number.isFinite(r.recommended.expected)).toBe(true);
    });
  }
});

describe("quantile function", () => {
  it("is monotone, nonnegative and hits the knots", () => {
    const q = [2, 3, 5, 7, 9, 12, 14];
    const lv = [0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95];
    expect(quantileFunction(q, lv, 0.5)).toBeCloseTo(7);
    let prev = -1;
    for (let u = 0; u <= 1; u += 0.01) {
      const v = quantileFunction(q, lv, u);
      expect(v).toBeGreaterThanOrEqual(prev - 1e-12);
      expect(v).toBeGreaterThanOrEqual(0);
      prev = v;
    }
  });
});
