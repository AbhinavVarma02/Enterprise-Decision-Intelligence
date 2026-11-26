import { useDeferredValue, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { rankCases, useCases, useData, type Meta } from "../data/load";
import { ErrorState, GateLedger, Loading, NotFound, OutcomeChip, Panel } from "../components/ui";
import { AlternativesTable, caseLocation, ordersText } from "../components/decision";
import { Heatmap } from "../components/charts";
import { STUDIO_LIMITS, modifiedSupply, studioEvaluate } from "../engine/studio";
import { orderIsFeasible } from "../engine/grid";
import type { DecisionCase, StudioMods, ValidatorParams } from "../engine/types";
import { append } from "../state/history";
import { money, pct, units } from "../lib/format";

const DEFAULTS: Required<StudioMods> = {
  demand_shift: 0,
  primary_delay_days: 0,
  cost_change: 0,
  budget_mult: 1,
  risk_weight: 0.5,
  alpha: 0.9,
  use_verified: false,
  primary_available: true,
  alternate_eligible: true,
  expedite_available: true,
};

function parseMods(sp: URLSearchParams): Required<StudioMods> {
  const num = (k: keyof typeof STUDIO_LIMITS, d: number) => {
    const v = Number(sp.get(k));
    if (!sp.has(k) || !Number.isFinite(v)) return d;
    const [lo, hi] = STUDIO_LIMITS[k];
    return Math.min(hi, Math.max(lo, v));
  };
  const bool = (k: string, d: boolean) => (sp.has(k) ? sp.get(k) === "1" : d);
  return {
    ...DEFAULTS,
    demand_shift: num("demand_shift", 0),
    primary_delay_days: Math.round(num("primary_delay_days", 0)),
    cost_change: num("cost_change", 0),
    budget_mult: num("budget_mult", 1),
    risk_weight: num("risk_weight", 0.5),
    use_verified: bool("use_verified", false),
    primary_available: bool("primary_available", true),
    alternate_eligible: bool("alternate_eligible", true),
    expedite_available: bool("expedite_available", true),
  };
}

export function Studio() {
  const { caseId } = useParams();
  const cases = useCases();
  const meta = useData<Meta>("meta");
  if (cases.status === "loading" || meta.status === "loading") return <Loading label="Loading scenario studio" />;
  if (cases.status === "error") return <ErrorState message={cases.error} />;
  if (meta.status === "error") return <ErrorState message={meta.error} />;
  const ranked = rankCases(cases.data);
  if (!caseId) return ranked.length ? <Navigate to={`/studio/${ranked[0].id}`} replace /> : <NotFound />;
  const c = ranked.find((x) => x.id === caseId);
  if (!c) return <NotFound />;
  return <StudioBody key={c.id} c={c} all={ranked} params={meta.data.validator_params} />;
}

function timedEvaluate(c: DecisionCase, mods: StudioMods, params: ValidatorParams) {
  const t0 = performance.now();
  try {
    const r = studioEvaluate(c, mods, params);
    return { ok: true as const, r, ms: performance.now() - t0 };
  } catch (e) {
    return { ok: false as const, error: (e as Error).message };
  }
}

function Slider({ id, label, value, min, max, step, format, onChange, help }: {
  id: string; label: string; value: number; min: number; max: number; step: number; format: (v: number) => string; onChange: (v: number) => void; help?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}<output htmlFor={id} className="num">{format(value)}</output></label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {help && <span className="help">{help}</span>}
    </div>
  );
}

function StudioBody({ c, all, params }: { c: DecisionCase; all: DecisionCase[]; params: ValidatorParams }) {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const mods = useMemo(() => parseMods(sp), [sp]);
  const deferred = useDeferredValue(mods);
  const updating = mods !== deferred;
  const [saved, setSaved] = useState(false);
  const set = (k: keyof StudioMods, v: number | boolean) => {
    const next = new URLSearchParams(sp);
    next.set(k, typeof v === "boolean" ? (v ? "1" : "0") : String(v));
    setSp(next, { replace: true });
    setSaved(false);
  };
  const result = useMemo(() => timedEvaluate(c, deferred, params), [c, deferred, params]);
  const verifiedDiffers = c.state.verified_on_hand_by_age.some((x, i) => Math.abs(x - c.state.recorded_on_hand_by_age[i]) > 1e-6);
  const changed = JSON.stringify(mods) !== JSON.stringify(DEFAULTS);

  const save = async () => {
    if (!result.ok || updating) return;
    const r = result.r;
    await append({
      case_id: c.id,
      title: c.title,
      entity: caseLocation(c),
      action: "scenario saved",
      validator_outcome: r.validation.outcome,
      orders: r.recommended.orders,
      expected_cost: r.recommended.expected,
      cvar: r.recommended.cvar,
      assumptions: Object.fromEntries(Object.entries(mods)) as Record<string, number | boolean>,
      note: "Scenario studio",
    });
    setSaved(true);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Scenario studio</h1>
          <p>Change an assumption and the recommended order, its risk and the validator's verdict are recalculated in your browser. The search covers a bounded grid of order combinations over the same demand scenarios as the decision workspace.</p>
        </div>
        <label className="row small" style={{ gap: 8 }}>
          <span className="muted">Decision</span>
          <select className="select" value={c.id} onChange={(e) => nav(`/studio/${e.target.value}?${sp.toString()}`)} aria-label="Choose a decision">
            {all.map((x) => <option key={x.id} value={x.id}>{x.title} ({caseLocation(x)})</option>)}
          </select>
        </label>
      </div>

      {result.ok && <div className="studio-quick-result" aria-live="polite">
        <div className="row"><OutcomeChip outcome={result.r.validation.outcome} /><span className="small muted">Best-scoring order</span></div>
        <strong>{ordersText(result.r.recommended.orders)}</strong>
        <span className="small muted num">{money(result.r.recommended.score)} risk-adjusted</span>
      </div>}
      <div className="studio-layout">
        <Panel title="Assumptions" hint={changed ? "Changed from the base case" : "Base case"}>
          <div className="stack" style={{ gap: 18 }}>
            <Slider id="s-demand" label="Demand versus forecast" value={mods.demand_shift} min={STUDIO_LIMITS.demand_shift[0]} max={STUDIO_LIMITS.demand_shift[1]} step={0.05}
              format={(v) => pct(v, 0, true)} onChange={(v) => set("demand_shift", v)} help="Scales every demand scenario." />
            <div className="field">
              <span className="small" style={{ fontWeight: 500 }} id="delay-l">Primary supplier delay</span>
              <div className="segmented" role="group" aria-labelledby="delay-l">
                {[0, 1, 2].map((d) => (
                  <button key={d} aria-pressed={mods.primary_delay_days === d} onClick={() => set("primary_delay_days", d)}>{d === 0 ? "On time" : `+${d} day${d > 1 ? "s" : ""}`}</button>
                ))}
              </div>
            </div>
            <Slider id="s-cost" label="Procurement cost change" value={mods.cost_change} min={STUDIO_LIMITS.cost_change[0]} max={STUDIO_LIMITS.cost_change[1]} step={0.05}
              format={(v) => pct(v, 0, true)} onChange={(v) => set("cost_change", v)} />
            <Slider id="s-budget" label="Procurement budget" value={mods.budget_mult} min={STUDIO_LIMITS.budget_mult[0]} max={STUDIO_LIMITS.budget_mult[1]} step={0.05}
              format={(v) => money(c.current_terms.budget * v)} onChange={(v) => set("budget_mult", v)} />
            <Slider id="s-risk" label="Weight on downside risk" value={mods.risk_weight} min={STUDIO_LIMITS.risk_weight[0]} max={STUDIO_LIMITS.risk_weight[1]} step={0.05}
              format={(v) => (v === 0 ? "expected cost only" : pct(v, 0))} onChange={(v) => set("risk_weight", v)}
              help="0 minimizes expected cost; higher values put more weight on the average of the worst 10% of scenarios." />
            <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="small" style={{ fontWeight: 500, marginBottom: 4 }}>Supply options</legend>
              <label className="toggle"><input type="checkbox" checked={mods.primary_available} onChange={(e) => set("primary_available", e.target.checked)} />Primary supplier delivering</label>
              <label className="toggle"><input type="checkbox" checked={mods.alternate_eligible} onChange={(e) => set("alternate_eligible", e.target.checked)} />Alternate supplier qualified</label>
              <label className="toggle"><input type="checkbox" checked={mods.expedite_available} onChange={(e) => set("expedite_available", e.target.checked)} />Expedited freight available</label>
              <label className="toggle" title={verifiedDiffers ? undefined : "The record matches physical stock for this decision"}>
                <input type="checkbox" checked={mods.use_verified} disabled={!verifiedDiffers} onChange={(e) => set("use_verified", e.target.checked)} />
                Use a verified stock count{verifiedDiffers ? "" : " (record already accurate)"}
              </label>
            </fieldset>
            <div className="row">
              <button className="btn" onClick={() => { setSp(new URLSearchParams(), { replace: true }); setSaved(false); }} disabled={!changed}>Reset assumptions</button>
              <button className="btn primary" onClick={save} disabled={!result.ok || updating || saved}>{saved ? "Saved to history" : "Save scenario"}</button>
            </div>
            <p className="xs faint">Bounds keep the browser calculation small. For wider sweeps or the full optimizer, run <code>edi benchmark</code> locally.</p>
          </div>
        </Panel>

        {result.ok ? <Results c={c} r={result.r} ms={result.ms} originalFeasible={orderIsFeasible(c.candidate.orders, modifiedSupply(c, deferred))} /> : (
          <div className="panel state" role="alert"><h2>This combination could not be evaluated</h2><p>{result.error}</p></div>
        )}
      </div>
    </>
  );
}

function Results({ c, r, ms, originalFeasible }: { c: DecisionCase; r: ReturnType<typeof studioEvaluate>; ms: number; originalFeasible: boolean }) {
  const [sel, setSel] = useState("act_now");
  const diff = r.original.score - r.recommended.score;
  return (
    <div className="stack" aria-live="polite">
      <Panel title="Best-scoring order under these assumptions" hint={`${r.grid_size} feasible combinations × ${c.scenarios.length} scenarios · ${ms.toFixed(0)} ms in this browser`}>
        <div className="row" style={{ alignItems: "flex-start", gap: 24 }}>
          <div style={{ flex: "1 1 260px" }}>
            <div className="row" style={{ marginBottom: 6 }}><OutcomeChip outcome={r.validation.outcome} /><span className="small muted">validator verdict</span></div>
            <p data-testid="studio-recommended" style={{ fontSize: "var(--fs-lg)", fontWeight: 600 }}>{ordersText(r.recommended.orders)} <span className="small muted num">at {money(r.recommended.score)} risk-adjusted</span></p>
            <p className="small muted" style={{ marginTop: 4 }}>{r.validation.reasons[0]}</p>
          </div>
          <div className="table-wrap" style={{ flex: "1 1 100%" }}>
          <table className="data stack-sm">
            <thead><tr><th scope="col">Order</th><th scope="col" className="r">Expected</th><th scope="col" className="r">Worst 10% avg</th><th scope="col" className="r">Risk-adjusted</th></tr></thead>
            <tbody>
              <tr><td className="full" style={{ fontWeight: 500 }}>Best-scoring order</td><td className="r num" data-label="Expected">{money(r.recommended.expected)}</td><td className="r num" data-label="Worst 10% avg">{money(r.recommended.cvar)}</td><td className="r num" data-label="Risk-adjusted">{money(r.recommended.score)}</td></tr>
              {originalFeasible ? <tr><td className="full" style={{ fontWeight: 500 }}>Original proposal</td><td className="r num" data-label="Expected">{money(r.original.expected)}</td><td className="r num" data-label="Worst 10% avg">{money(r.original.cvar)}</td><td className="r num" data-label="Risk-adjusted">{money(r.original.score)}</td></tr>
                : <tr><td className="full">Original proposal</td><td colSpan={3} className="full muted">Infeasible under these terms</td></tr>}
            </tbody>
            <caption>{originalFeasible ? `Re-planning ${diff >= 0 ? "reduces" : "raises"} risk-adjusted cost by ${money(Math.abs(diff))} over ${r.horizon} days.` : "The search compares orders that meet the current supply and budget constraints."}</caption>
          </table>
          </div>
        </div>
      </Panel>
      <Panel title={r.surface.measure === "risk_adjusted" ? "Risk-adjusted cost by order mix" : "Expected cost by order mix"} hint={`Expedite fixed at ${units(r.recommended.orders[2])} units`}>
        <Heatmap rows={r.surface.primary} cols={r.surface.alternate} values={r.surface.value} measure={r.surface.measure === "risk_adjusted" ? "risk-adjusted cost" : "expected cost"}
          mark={[r.recommended.orders[0], r.recommended.orders[1]]} candidate={[c.candidate.orders[0], c.candidate.orders[1]]}
          rowLabel="Primary units" colLabel="Alternate units" />
      </Panel>
      <Panel title="Cost of waiting or doing less" pad={false}>
        <div style={{ padding: "4px 8px 8px" }}><AlternativesTable alts={r.alternatives} selected={sel} onSelect={setSel} caption={`Evaluated over ${r.horizon} days. Units that waiting pushes past the horizon are charged and credited as leftover stock.`} /></div>
      </Panel>
      <Panel title="Validation of the recommended order" pad={false}><GateLedger gates={r.validation.gates} /></Panel>
    </div>
  );
}
