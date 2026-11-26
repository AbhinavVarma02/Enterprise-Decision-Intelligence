/** Loads the versioned JSON artifacts produced by `edi export-web`. */
import { useEffect, useState } from "react";
import type { DecisionCase, ValidatorParams } from "../engine/types";

export interface Meta {
  app_version: string;
  data_source: string;
  data_label: string;
  run_id: string;
  config_hash: string;
  git_sha: string;
  generated_at: string;
  protocol_version: string;
  test_window_days: number[];
  validator_params: ValidatorParams;
  currency_note: string;
  attribution: string;
}

export interface CI {
  mean: number;
  lo: number;
  hi: number;
  n: number;
}

// The benchmark, forecast, data-quality and secondary-domain files are large nested documents.
// They are typed loosely here and narrowed where used.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Loose = any;

const cache = new Map<string, Promise<unknown>>();

export function fetchJson<T>(name: string): Promise<T> {
  if (!cache.has(name)) {
    const p = fetch(`/data/${name}.json`, { cache: "no-cache" }).then(async (r) => {
      if (!r.ok) throw new Error(`Could not load ${name}.json (HTTP ${r.status}).`);
      return r.json();
    });
    p.catch(() => cache.delete(name));
    cache.set(name, p);
  }
  return cache.get(name) as Promise<T>;
}

export type Load<T> = { status: "loading" } | { status: "error"; error: string } | { status: "ready"; data: T };

export function useData<T>(name: string): Load<T> {
  const [state, setState] = useState<Load<T>>({ status: "loading" });
  useEffect(() => {
    let live = true;
    fetchJson<T>(name)
      .then((data) => live && setState({ status: "ready", data }))
      .catch((e: Error) => live && setState({ status: "error", error: e.message }));
    return () => {
      live = false;
    };
  }, [name]);
  return state;
}

export function useCases(): Load<DecisionCase[]> {
  const s = useData<{ cases: DecisionCase[] }>("cases");
  if (s.status !== "ready") return s;
  return { status: "ready", data: s.data.cases };
}

/** Ranked exception queue: unresolved cases first, then by cost of inaction net of investigation. */
export function rankCases(cases: DecisionCase[]): DecisionCase[] {
  return cases.slice().sort((a, b) => {
    const ra = a.validation.outcome === "recommend" ? 1 : 0;
    const rb = b.validation.outcome === "recommend" ? 1 : 0;
    if (ra !== rb) return ra - rb;
    const na = a.priority.cost_of_inaction - (a.validation.outcome === "investigate" ? a.investigation_cost : 0);
    const nb = b.priority.cost_of_inaction - (b.validation.outcome === "investigate" ? b.investigation_cost : 0);
    return nb - na;
  });
}
