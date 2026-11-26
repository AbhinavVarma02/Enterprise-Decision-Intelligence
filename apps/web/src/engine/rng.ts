/** Seeded sampling for imported candidates (browser only; not bit-identical to numpy). */
import { quantileFunction } from "./evaluator";

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(rand: () => number): number {
  let u = 0;
  while (u === 0) u = rand();
  const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function ndtr(z: number): number {
  // Abramowitz-Stegun 7.1.26 approximation of the normal CDF
  const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
  const y = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(z * z) / 2);
  return z >= 0 ? 0.5 * (1 + y) : 0.5 * (1 - y);
}

export function samplePaths(quantiles: number[][], levels: number[], k: number, rho: number, seed: number): number[][] {
  const rand = mulberry32(seed);
  const out: number[][] = [];
  for (let i = 0; i < k; i++) {
    const z0 = normal(rand);
    out.push(quantiles.map((q) => quantileFunction(q, levels, ndtr(Math.sqrt(rho) * z0 + Math.sqrt(1 - rho) * normal(rand)))));
  }
  return out;
}

export function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
