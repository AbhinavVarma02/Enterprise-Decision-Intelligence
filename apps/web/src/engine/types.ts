/** Types shared by the engine and the UI. Field names follow the Python export (snake_case). */

export interface Econ {
  price: number;
  unit_cost: number;
  shelf_life: number;
  holding: number;
  disposal: number;
  goodwill: number;
  terminal_waste_risk: number;
  currency?: string;
}

export interface Resource {
  name: string;
  lead_days: number;
  unit_cost: number;
  capacity: number;
  min_quantity: number;
  eligible: boolean;
  available: boolean;
  attributes: Record<string, number | string | boolean>;
}

export interface Terms {
  resources: Resource[];
  budget: number;
  min_commitment?: number;
}

export interface Supply {
  leads: number[];
  unitCosts: number[];
  capacities: number[]; // usable capacity: 0 when ineligible or unavailable
  moqs: number[];
  budget: number;
  minCommitment: number;
  approvalThreshold: number;
  maxExpediteShare: number;
  resources: Resource[];
}

export type Outcome = "recommend" | "investigate" | "defer" | "escalate" | "reject";
export type GateStatus = "pass" | "warn" | "fail";

export interface Gate {
  gate: string;
  name: string;
  status: GateStatus;
  summary: string;
}

export interface ValidationResult {
  outcome: Outcome;
  reasons: string[];
  explanation: string;
  recommended_action: Record<string, number> | null;
  metrics: Record<string, number | null>;
  gates: Gate[];
  value_of_information: {
    evpi: number;
    value_vs_candidate: number;
    investigation_cost: number;
    worth_investigating: boolean;
    labels: string[];
    probabilities: number[];
    input: string;
  } | null;
}

export interface Alternative {
  key: string;
  label: string;
  orders: number[];
  expected_cost: number;
  cvar: number;
  p90: number;
  expected_fill_rate: number;
  expected_waste_units: number;
  governance_cost: number;
  prob_over_tolerance?: number;
  arrives_after_horizon?: number;
  delta_vs_act_now: number;
}

export interface FanPoint {
  day: number;
  p5: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
}

export interface DecisionCase {
  id: string;
  title: string;
  entity: { series_id: string; store: string; product: string; category: string };
  day: number;
  date: string;
  condition: string;
  events: string[];
  mu: number;
  revenue_scale: number;
  economics: Econ;
  state: { recorded_on_hand_by_age: number[]; verified_on_hand_by_age: number[]; pipeline_by_day: number[] };
  plan_terms: Terms;
  current_terms: Terms;
  approval_threshold: number;
  max_expedite_share: number;
  freshness_max_age_hours: number;
  data_age_hours: number;
  history_days_missing: number;
  signals: Record<string, number>;
  investigation_cost: number;
  review_cost: number;
  forecast: { levels: number[]; quantiles: number[][]; model: string; staleness_days: number };
  scenarios: number[][];
  candidate: { orders: number[]; policy: string; claimed_expected_cost: number | null };
  validation: ValidationResult;
  alternatives: Alternative[];
  horizon_days: number;
  priority: { cost_of_inaction: number; days_of_cover: number; downside: number; investigation_cost: number; feasible: boolean };
  fan: FanPoint[];
}

export interface ValidatorParams {
  financial_tol_warn: number;
  financial_tol_fail: number;
  cvar_alpha: number;
  loss_tolerance_mult: number;
  stress_tolerance_mult: number;
  hedge_cost_share: number;
  uncertainty_ratio_warn: number;
  defer_cost_share: number;
  anomaly_min_stockout_hours: number;
  anomaly_min_carryover_days: number;
  anomaly_jump_ratio: number;
  prior_clean: number;
  prior_anomalous: number;
  error_multipliers: number[];
  n_scenarios: number;
  rho: number;
  seed: number;
}

export interface StudioMods {
  demand_shift?: number;
  primary_delay_days?: number;
  cost_change?: number;
  budget_mult?: number;
  risk_weight?: number;
  alpha?: number;
  use_verified?: boolean;
  primary_available?: boolean;
  alternate_eligible?: boolean;
  expedite_available?: boolean;
}

export interface StudioResult {
  horizon: number;
  grid_size: number;
  best_expected: { orders: number[]; expected: number; cvar: number };
  recommended: { orders: number[]; expected: number; cvar: number; score: number };
  original: { orders: number[]; expected: number; cvar: number; score: number };
  validation: ValidationResult;
  alternatives: Alternative[];
  surface: { primary: number[]; alternate: number[]; value: (number | null)[][]; measure: "risk_adjusted" | "expected" };
}
