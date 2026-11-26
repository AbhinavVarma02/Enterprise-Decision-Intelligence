/** Formatting helpers. All currency figures in this app are assumed economics, labelled in the UI. */
export function money(x: number | null | undefined, opts: { signed?: boolean } = {}): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "n/a";
  const v = Math.abs(x);
  const body =
    v >= 100
      ? v.toLocaleString("en-US", { maximumFractionDigits: 0 })
      : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const zero = Number(body.replace(/,/g, "")) === 0;
  const sign = zero ? "" : x < 0 ? "−" : opts.signed && x > 0 ? "+" : "";
  return `${sign}$${body}`;
}

export function units(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "n/a";
  return x.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function pct(x: number | null | undefined, digits = 1, signed = false): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "n/a";
  const s = (100 * x).toFixed(digits);
  // A value that rounds to zero prints as 0.0%, never as -0.0% or +0.0%.
  if (Number(s) === 0) return `${(0).toFixed(digits)}%`;
  return `${signed && x > 0 ? "+" : ""}${s.replace("-", "\u2212")}%`;
}

export function titleCase(s: string): string {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export const OUTCOME_LABEL: Record<string, string> = {
  recommend: "Recommend",
  investigate: "Investigate",
  defer: "Defer",
  escalate: "Escalate",
  reject: "Reject",
  execute: "Executed",
};

export const OUTCOME_HEADLINE: Record<string, string> = {
  recommend: "Recommend the proposed order",
  investigate: "Verify the record before ordering",
  defer: "Wait for fresh data",
  escalate: "Send to a planner for review",
  reject: "Reject the proposed order",
};

export const EVENT_LABEL: Record<string, string> = {
  inventory_record_error: "Inventory record error",
  stale_supplier_snapshot: "Stale supplier terms",
  stale_sales_history: "Late sales data",
  forecast_shift: "Demand above forecast",
  supplier_failure: "Supplier failure",
  lead_time_increase: "Lead time increase",
  capacity_reduction: "Capacity cut",
  cost_increase: "Cost increase",
  transport_disruption: "Freight disruption",
  budget_reduction: "Budget cut",
  demand_spike: "Demand spike",
  demand_collapse: "Demand collapse",
};

export const POLICY_LABEL: Record<string, string> = {
  P1: "Base-stock rule",
  P2: "Point forecast + MILP",
  P3: "Quantiles + expected-cost MILP",
  P4: "Quantiles + mean-CVaR MILP",
  P5a: "Validation over P3",
  P5b: "Validation over P4",
  ORACLE: "Oracle (hindsight)",
};

export const CATEGORY_LABEL: Record<string, string> = {
  leafy: "Leafy greens",
  fruit: "Fruit",
  dairy: "Dairy",
  protein: "Meat and fish",
};
