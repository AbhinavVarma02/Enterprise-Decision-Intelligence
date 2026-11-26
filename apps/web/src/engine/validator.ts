/**
 * Browser port of the independent validation engine (edi.validation.engine with the inventory adapter).
 * It evaluates supplied demand scenarios (it never samples), so results match the Python reference on
 * the golden fixtures. Outcome precedence: reject > defer/escalate (stale or missing evidence) >
 * investigate > escalate (risk) > escalate (approval) > recommend. There is no blended score.
 */
import { actionGrid, supplyFromTerms } from "./grid";
import { argmin, cvar, evaluateActions, horizonFor, mean, std } from "./evaluator";
import type { Econ, Gate, GateStatus, Outcome, Terms, ValidationResult, ValidatorParams } from "./types";

const TOL = 1e-6;
const NAMES = ["primary", "alternate", "expedite"];

export interface CandidateInput {
  decision_id: string;
  typical_daily_volume: number;
  age_hours: number;
  history_days_missing: number;
  on_hand_by_age: number[] | null;
  pipeline_by_day: number[] | null;
  action: Record<string, number>;
  plan_terms: Terms;
  plan_econ: Econ;
  forecast: { levels: number[]; quantiles: number[][] } | null;
  claimed_expected_cost: number | null;
  claimed_n_scenarios: number;
  cvar_alpha: number;
}

export interface ContextInput {
  terms: Terms;
  econ: Econ;
  approval_threshold: number;
  max_share: Record<string, number>;
  freshness_max_age_hours: number;
  signals: Record<string, number>;
  investigation_cost: number;
  review_cost: number;
}

const fmt = (x: number) =>
  x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usd = (x: number) => (x < 0 ? `-$${fmt(Math.abs(x))}` : `$${fmt(x)}`);
const stripDot = (s: string) => s.replace(/\.+$/, "");

function evalWith(
  cand: CandidateInput,
  terms: Terms,
  econ: Econ,
  actions: number[][],
  S: number[][],
  h: number,
  onHand?: number[],
): Float64Array[] {
  const sup = supplyFromTerms(terms);
  const pipe = new Array(h).fill(0);
  const p = cand.pipeline_by_day ?? [];
  for (let i = 0; i < Math.min(h, p.length); i++) pipe[i] = p[i];
  const acts = actions.map((a) => a.map((q, i) => Math.min(q, sup.capacities[i])));
  const coh = (onHand ?? cand.on_hand_by_age ?? []).slice(0, econ.shelf_life);
  while (coh.length < econ.shelf_life) coh.push(0);
  const Sh = S.map((row) => row.slice(0, h));
  return evaluateActions(coh, pipe, acts, sup.leads, sup.unitCosts, Sh, econ).cost;
}

export function validateCandidate(
  cand: CandidateInput,
  ctx: ContextInput,
  params: ValidatorParams,
  scenarios: number[][] | null,
): ValidationResult {
  const metrics: Record<string, number | null> = {};
  const reasons: string[] = [];
  const auth = new Map(ctx.terms.resources.map((r) => [r.name, r]));
  const planRes = cand.plan_terms.resources;
  const names = planRes.map((r) => r.name);
  const a = names.map((n) => cand.action[n] ?? 0);
  const rev = cand.typical_daily_volume * ctx.econ.price;
  metrics.revenue_scale = rev;

  // G6
  const missing: string[] = [];
  if (!cand.forecast) missing.push("forecast distribution");
  if (!cand.on_hand_by_age) missing.push("state 'on_hand_by_age'");
  if (!cand.pipeline_by_day) missing.push("state 'pipeline_by_day'");
  const unknownAuth = names.filter((n) => !auth.has(n));
  if (unknownAuth.length) missing.push(`authoritative terms for ${unknownAuth.join(", ")}`);
  const g6: Gate = {
    gate: "G6",
    name: "Missing critical evidence",
    status: missing.length ? "fail" : "pass",
    summary: missing.length ? "Missing: " + missing.join(", ") : "Required evidence present.",
  };

  // G1
  const stale = cand.age_hours > ctx.freshness_max_age_hours;
  const histGap = cand.history_days_missing > 1;
  let anomaly = false;
  const anomReasons: string[] = [];
  if (!missing.length) {
    const coh = cand.on_hand_by_age ?? [];
    const carry = coh.length > 1 ? coh.slice(1).reduce((s, x) => s + x, 0) : coh.reduce((s, x) => s + x, 0);
    const so = ctx.signals.stockout_hours_yesterday ?? 0;
    const jump = ctx.signals.record_jump_ratio ?? 0;
    if (so >= params.anomaly_min_stockout_hours && carry >= params.anomaly_min_carryover_days * cand.typical_daily_volume)
      anomReasons.push(
        `shelf was out of stock for ${so.toFixed(0)} h yesterday, yet the record shows ${carry.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} units carried over`,
      );
    if (jump > params.anomaly_jump_ratio)
      anomReasons.push(`recorded on-hand moved ${jump.toFixed(1)} days of demand more than receipts and sales explain`);
    anomaly = anomReasons.length > 0;
  }
  const g1Parts: string[] = [];
  if (stale) g1Parts.push(`snapshot is ${cand.age_hours.toFixed(0)} h old (limit ${ctx.freshness_max_age_hours.toFixed(0)} h)`);
  if (histGap) g1Parts.push(`${cand.history_days_missing} days of sales history missing`);
  g1Parts.push(...anomReasons);
  const g1: Gate = {
    gate: "G1",
    name: "Data integrity and freshness",
    status: stale || histGap ? "fail" : anomaly ? "warn" : "pass",
    summary: g1Parts.length ? g1Parts.join("; ") : "Snapshot is current and internally consistent.",
  };

  // G2
  const viol: string[] = [];
  const warn2: string[] = [];
  names.forEach((nm, i) => {
    const q = a[i];
    const r = auth.get(nm);
    if (!r) return;
    if (q < -TOL) viol.push(`${nm} quantity is negative`);
    if (q > TOL && !(r.eligible && r.available)) viol.push(`${nm} supplier is not ${!r.eligible ? "qualified" : "available"}`);
    if (q > r.capacity * (1 + 1e-6) + TOL) viol.push(`${nm} order of ${fmt(q)} units exceeds current capacity of ${fmt(r.capacity)}`);
    if (q > TOL && q < r.min_quantity - TOL) viol.push(`${nm} order of ${fmt(q)} units is below the minimum of ${fmt(r.min_quantity)}`);
    const cr = planRes[i];
    if (cr.lead_days !== r.lead_days) warn2.push(`${nm}: plan assumed lead ${cr.lead_days} d, current terms say ${r.lead_days} d`);
    if (Math.abs(cr.unit_cost - r.unit_cost) > 1e-6 * Math.max(1, r.unit_cost))
      warn2.push(`${nm}: plan priced at ${usd(cr.unit_cost)}, current price ${usd(r.unit_cost)}`);
  });
  const authCosts = names.map((n, i) => (auth.get(n) ?? planRes[i]).unit_cost);
  const committed = names.map((n, i) => {
    const r = auth.get(n) ?? planRes[i];
    return r.attributes?.committed === undefined ? true : Boolean(r.attributes.committed);
  });
  let spend = 0;
  for (let i = 0; i < a.length; i++) spend += (committed[i] ? a[i] : 0) * authCosts[i];
  if (spend > ctx.terms.budget * (1 + 1e-6) + TOL) viol.push(`spend of ${usd(spend)} exceeds the budget of ${usd(ctx.terms.budget)}`);
  const minC = ctx.terms.min_commitment ?? 0;
  if (minC > 0 && a[0] + TOL < minC) viol.push(`${names[0]} order is below the contractual minimum of ${fmt(minC)}`);
  metrics.spend = spend;
  const g2: Gate = {
    gate: "G2",
    name: "Constraint satisfaction",
    status: viol.length ? "fail" : warn2.length ? "warn" : "pass",
    summary: (viol.length ? viol : warn2).join("; ") || "All hard constraints hold under current terms.",
  };

  let g3: Gate;
  let g4: Gate;
  let g5: Gate;
  let bestAction: Record<string, number> | null = null;
  let voi: ValidationResult["value_of_information"] = null;
  let hedgeAction: Record<string, number> | null = null;
  const canEval = cand.forecast !== null && missing.length === 0 && scenarios !== null;
  let S: number[][] = [];
  let grid: number[][] = [];
  let h = 2;
  if (canEval && cand.forecast && scenarios) {
    S = scenarios;
    const authSup = supplyFromTerms(ctx.terms);
    h = Math.min(cand.forecast.quantiles.length, horizonFor(authSup.leads, authSup.capacities));
    grid = actionGrid(authSup, h);
    const Cg = evalWith(cand, ctx.terms, ctx.econ, grid, S, h);
    const Cc = evalWith(cand, ctx.terms, ctx.econ, [a], S, h)[0];
    const eC = mean(Cc);
    const cvC = cvar(Cc, params.cvar_alpha);
    const eG = Cg.map((c) => mean(c));
    const cvG = Cg.map((c) => cvar(c, params.cvar_alpha));
    const ib = argmin(eG);
    bestAction = Object.fromEntries(names.map((n, i) => [n, grid[ib][i]]));
    let over = 0;
    for (let k = 0; k < Cc.length; k++) if (Cc[k] > eC + rev) over++;
    Object.assign(metrics, {
      expected_cost: eC,
      cvar: cvC,
      best_grid_expected_cost: eG[ib],
      prob_loss_over_tolerance: over / Cc.length,
    });

    // G3
    const Cown = evalWith(cand, cand.plan_terms, cand.plan_econ, [a], S, h)[0];
    const eOwn = mean(Cown);
    const impact = eC - eOwn;
    const scale3 = Math.max(Math.abs(eC), 0.25 * rev, 1e-9);
    const impactRel = Math.abs(impact) / scale3;
    const claimed = cand.claimed_expected_cost;
    const kClaim = cand.claimed_n_scenarios;
    const se = std(Cown, 1) * Math.sqrt(1 / Cown.length + (kClaim ? 1 / kClaim : 1));
    const claimGap = claimed === null ? null : Math.abs(claimed - eOwn);
    const tolFail = Math.max(params.financial_tol_fail * scale3, 4 * se);
    const tolWarn = Math.max(params.financial_tol_warn * scale3, 2 * se);
    let st3: GateStatus = "pass";
    const notes3: string[] = [];
    if (impactRel > params.financial_tol_fail) {
      st3 = "fail";
      notes3.push(
        impact > 0
          ? `plan terms understate cost by ${usd(impact)} versus current terms`
          : `plan terms overstate cost by ${usd(-impact)} versus current terms`,
      );
    } else if (impactRel > params.financial_tol_warn) {
      st3 = "warn";
      notes3.push(`plan terms differ from current terms by ${usd(impact)}`);
    }
    if (claimGap === null) {
      if (st3 === "pass") st3 = "warn";
      notes3.push(`no claimed cost to reconcile; independent estimate ${usd(eC)}`);
    } else if (claimGap > tolFail) {
      st3 = "fail";
      notes3.push(
        `claimed expected cost ${usd(claimed ?? 0)} does not reconcile with ${usd(eOwn)} recomputed on its own terms (tolerance ${usd(tolFail)})`,
      );
    } else if (claimGap > tolWarn && st3 === "pass") {
      st3 = "warn";
      notes3.push(`claimed ${usd(claimed ?? 0)} vs recomputed ${usd(eOwn)}`);
    }
    g3 = {
      gate: "G3",
      name: "Financial consistency",
      status: st3,
      summary: notes3.length
        ? notes3.join("; ")
        : `Claimed ${usd(claimed ?? 0)} reconciles with ${usd(eOwn)} recomputed; current terms change cost by ${usd(impact)}.`,
    };
    metrics.financial_relative_difference = impactRel;
    metrics.claim_gap = claimGap;

    // G4
    const hedge = eG.map((e) => e <= eC + params.hedge_cost_share * rev);
    const anyHedge = hedge.some(Boolean);
    let minCvHedge = Infinity;
    let ih = ib;
    cvG.forEach((v, i) => {
      if (hedge[i] && v < minCvHedge) {
        minCvHedge = v;
        ih = i;
      }
    });
    const tailGain = anyHedge ? cvC - minCvHedge : 0;
    const tol4 = params.loss_tolerance_mult * 0.25 * rev;
    const lv = cand.forecast.levels;
    let unc: number | null = null;
    const i10 = lv.indexOf(0.1);
    const i50 = lv.indexOf(0.5);
    const i90 = lv.indexOf(0.9);
    if (i10 >= 0 && i50 >= 0 && i90 >= 0) {
      const rows = cand.forecast.quantiles;
      unc = mean(rows.map((q) => (q[i90] - q[i10]) / Math.max(q[i50], 1e-9)));
    }
    const st4: GateStatus =
      tailGain > tol4 ? "fail" : tailGain > tol4 / 2 || (unc ?? 0) > params.uncertainty_ratio_warn ? "warn" : "pass";
    hedgeAction = Object.fromEntries(names.map((n, i) => [n, grid[ih][i]]));
    g4 = {
      gate: "G4",
      name: "Uncertainty and downside risk",
      status: st4,
      summary:
        `Expected ${usd(eC)}; worst-${100 - Math.round(params.cvar_alpha * 100)}% average ${usd(cvC)}. ` +
        (tailGain > 1e-9
          ? `A hedge within ${usd(params.hedge_cost_share * rev)} of expected cost lowers it by ${usd(tailGain)} (tolerance ${usd(tol4)}).`
          : "No cheaper-tail alternative found."),
    };
    metrics.tail_gain = tailGain;

    // G5
    const cases: [string, (acts: number[][]) => Float64Array[]][] = [
      ["primary order not delivered", (acts) => evalWith(cand, ctx.terms, ctx.econ, acts.map((x) => [0, x[1], x[2]]), S, h)],
      ["demand 40% above forecast", (acts) => evalWith(cand, ctx.terms, ctx.econ, acts, S.map((r) => r.map((x) => x * 1.4)), h)],
      ["demand 40% below forecast", (acts) => evalWith(cand, ctx.terms, ctx.econ, acts, S.map((r) => r.map((x) => x * 0.6)), h)],
    ];
    let worstC = -Infinity;
    const worstG = new Array(grid.length).fill(-Infinity);
    for (const [, fn] of cases) {
      const sc = mean(fn([a])[0]);
      const sg = fn(grid).map((c) => mean(c));
      worstC = Math.max(worstC, sc);
      for (let i = 0; i < grid.length; i++) worstG[i] = Math.max(worstG[i], sg[i]);
    }
    let minWorst = Infinity;
    for (let i = 0; i < grid.length; i++) if (hedge[i]) minWorst = Math.min(minWorst, worstG[i]);
    const robustGain = anyHedge ? worstC - minWorst : 0;
    const tol5 = params.stress_tolerance_mult * 0.25 * rev;
    g5 = {
      gate: "G5",
      name: "Stress-case resilience",
      status: robustGain > tol5 ? "fail" : robustGain > tol5 / 2 ? "warn" : "pass",
      summary: `Worst stress-case cost ${usd(worstC)}; a cheap hedge would cap it ${usd(robustGain)} lower (tolerance ${usd(tol5)}).`,
    };
    metrics.stress_gain = robustGain;

    // value of verification
    if (anomaly) {
      const coh = cand.on_hand_by_age ?? [];
      const mults = params.error_multipliers;
      const p1 = params.prior_anomalous;
      const others = (1 - p1) / (mults.length - 1);
      const probs = mults.map((m) => (m === 1 ? p1 : others));
      const labels = mults.map((m) => (m === 1 ? "record correct" : `carried-over stock is ${Math.round(100 * m)}% of record`));
      const costs: number[][] = []; // [state][action]
      const candBy: number[] = [];
      for (const m of mults) {
        const tr = coh.map((x, i) => (i >= 1 ? x * m : x));
        costs.push(evalWith(cand, ctx.terms, ctx.econ, grid, S, h, tr).map((c) => mean(c)));
        candBy.push(mean(evalWith(cand, ctx.terms, ctx.econ, [a], S, h, tr)[0]));
      }
      const expected = grid.map((_, i) => probs.reduce((s, p, j) => s + p * costs[j][i], 0));
      const v0 = expected[argmin(expected)];
      let v1 = 0;
      probs.forEach((p, j) => (v1 += p * costs[j][argmin(costs[j])]));
      const candPrior = probs.reduce((s, p, j) => s + p * candBy[j], 0);
      const valueVs = Math.max(0, candPrior - v1);
      voi = {
        evpi: Math.max(0, v0 - v1),
        value_vs_candidate: valueVs,
        investigation_cost: ctx.investigation_cost,
        worth_investigating: valueVs > ctx.investigation_cost,
        labels,
        probabilities: probs,
        input: "on-hand inventory",
      };
      metrics.evpi = voi.evpi;
      metrics.value_vs_candidate = valueVs;
    }
  } else {
    const ph = (gate: string, name: string): Gate => ({ gate, name, status: "warn", summary: "Not evaluated: no usable forecast." });
    g3 = ph("G3", "Financial consistency");
    g4 = ph("G4", "Uncertainty and downside risk");
    g5 = ph("G5", "Stress-case resilience");
  }

  // G7
  const gov: string[] = [];
  if (spend > ctx.approval_threshold + TOL)
    gov.push(`spend of ${usd(spend)} is above the approval threshold of ${usd(ctx.approval_threshold)}`);
  const committedQ = a.filter((_, i) => committed[i]);
  const totalQ = committedQ.length ? committedQ.reduce((s, x) => s + x, 0) : a.reduce((s, x) => s + x, 0);
  const usable = new Map(names.filter((n) => auth.has(n)).map((n) => {
    const r = auth.get(n)!;
    return [n, r.eligible && r.available && r.capacity > TOL] as const;
  }));
  for (const [nm, share] of Object.entries(ctx.max_share)) {
    const othersUsable = [...usable.entries()].some(([k, v]) => k !== nm && v);
    if (names.includes(nm) && totalQ > TOL && othersUsable) {
      const s = a[names.indexOf(nm)] / totalQ;
      if (s > share + 1e-9)
        gov.push(`${nm} share ${Math.round(100 * s)}% exceeds policy ${Math.round(100 * share)}% while standard supply is available`);
    }
  }
  const g7: Gate = {
    gate: "G7",
    name: "Governance and approval",
    status: gov.length ? "warn" : "pass",
    summary: gov.length ? "Approval required: " + gov.join("; ") : "Within delegated authority.",
  };

  const gates = [g1, g2, g3, g4, g5, g6, g7];
  const by = Object.fromEntries(gates.map((g) => [g.gate, g]));
  let outcome: Outcome = "recommend";
  let recommended: Record<string, number> | null = null;
  if (by.G2.status === "fail" || by.G3.status === "fail") {
    outcome = "reject";
    reasons.push(by.G2.status === "fail" ? by.G2.summary : by.G3.summary);
    recommended = bestAction;
  } else if (by.G1.status === "fail" || by.G6.status === "fail") {
    let waitCost: number | null = null;
    if (canEval) {
      const zero = [[0, 0, 0]];
      waitCost = mean(evalWith(cand, ctx.terms, ctx.econ, zero, S, h)[0]) - (metrics.best_grid_expected_cost ?? 0);
      metrics.cost_of_waiting = waitCost;
    }
    if (waitCost !== null && waitCost <= params.defer_cost_share * rev) {
      outcome = "defer";
      const lead = by.G1.status === "fail" ? by.G1.summary : by.G6.summary;
      reasons.push(`${stripDot(lead)}. Waiting a day costs about ${usd(waitCost)}.`);
    } else {
      outcome = "escalate";
      reasons.push(
        stripDot(by.G1.status === "fail" ? by.G1.summary : by.G6.summary) +
          ". Waiting is expensive or cannot be priced, so a planner must decide.",
      );
    }
  } else if (voi && voi.worth_investigating) {
    outcome = "investigate";
    reasons.push(
      `${stripDot(by.G1.summary)}. Verifying it is worth about ${usd(voi.value_vs_candidate)} against a cost of ${usd(ctx.investigation_cost)}.`,
    );
  } else if (by.G4.status === "fail" || by.G5.status === "fail") {
    outcome = "escalate";
    reasons.push(by.G4.status === "fail" ? by.G4.summary : by.G5.summary);
    recommended = hedgeAction ?? bestAction;
  } else if (by.G7.status === "warn") {
    outcome = "escalate";
    reasons.push(by.G7.summary);
  } else {
    reasons.push("All gates passed or raised only warnings that do not change the action.");
  }
  const result: ValidationResult = {
    outcome,
    reasons,
    explanation: "",
    recommended_action: recommended,
    metrics,
    gates,
    value_of_information: voi,
  };
  result.explanation = explain(cand.action, result, cand.cvar_alpha);
  return result;
}

const VERB: Record<Outcome, string> = {
  recommend: "Recommend",
  investigate: "Investigate before acting",
  defer: "Defer",
  escalate: "Escalate for review",
  reject: "Reject",
};

function money(x: number | null | undefined): string {
  if (x === null || x === undefined) return "n/a";
  const sign = x < 0 ? "-" : "";
  const v = Math.abs(x);
  return v >= 100
    ? `${sign}$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
    : `${sign}$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function describeAction(action: Record<string, number>, unit = "units"): string {
  const parts = Object.entries(action)
    .filter(([, v]) => v > 1e-6)
    .map(([k, v]) => `${v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${unit} via ${k}`);
  return parts.length ? parts.join(", ") : "no new order";
}

/** Same template as edi.explain.templates. */
export function explain(action: Record<string, number>, rep: ValidationResult, alpha: number): string {
  const m = rep.metrics;
  const lines = [`${VERB[rep.outcome]}: ${describeAction(action)}.`];
  if (m.expected_cost !== undefined && m.expected_cost !== null) {
    const a = Math.round(alpha * 100);
    lines.push(`Modeled expected cost ${money(m.expected_cost)}; average of the worst ${100 - a}% of scenarios ${money(m.cvar)}.`);
  }
  const fails = rep.gates.filter((g) => g.status === "fail");
  const warns = rep.gates.filter((g) => g.status === "warn");
  for (const g of fails.slice(0, 2)) lines.push(`${g.name} failed: ${stripDot(g.summary)}.`);
  if (rep.outcome === "investigate" && rep.value_of_information) {
    const v = rep.value_of_information;
    lines.push(
      `Checking ${v.input} is worth about ${money(v.value_vs_candidate)} in avoided cost, more than its ${money(v.investigation_cost)} cost.`,
    );
  }
  if (rep.recommended_action && (rep.outcome === "reject" || rep.outcome === "escalate"))
    lines.push(`Suggested alternative: ${describeAction(rep.recommended_action)}.`);
  if (!fails.length && warns.length && rep.outcome === "recommend") lines.push(`Noted: ${stripDot(warns[0].summary)}.`);
  return lines.join(" ");
}

export { NAMES };
