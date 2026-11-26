import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { z } from "zod";
import { MAX_IMPORT_BYTES, resetLog, useLog, verify } from "../state/history";
import { exportLog, importLog } from "../state/history-io";
import { Empty, OutcomeChip, Panel } from "../components/ui";
import { ordersText } from "../components/decision";
import { money } from "../lib/format";
import { validateCandidate } from "../engine/validator";
import { hashSeed, samplePaths } from "../engine/rng";
import { useData, type Meta } from "../data/load";
import type { ValidationResult } from "../engine/types";

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function HistoryPage() {
  const log = useLog();
  const [chain, setChain] = useState<string>("Checking");
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let live = true;
    verify(log).then((v) => live && setChain(v.ok ? "Intact" : `Broken at entry ${(v.brokenAt ?? 0) + 1}`));
    return () => {
      live = false;
    };
  }, [log]);

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) return setMsg("That file is larger than 1 MB.");
    const res = await importLog(await file.text());
    setMsg(res.ok ? `Imported ${res.count} decisions. The hash chain verified.` : res.error);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Decision history</h1>
          <p>Approvals, escalations and saved scenarios from this browser. Entries are hash-chained so accidental edits are detectable, but local storage is not tamper-proof and is not a system of record. Everything here is simulated.</p>
        </div>
        <div className="row">
          <button className="btn" onClick={() => download("edi-decision-log.json", exportLog(log))} disabled={!log.length}>Export log</button>
          <button className="btn" onClick={() => fileRef.current?.click()}>Import log</button>
          <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => onImport(e.target.files?.[0])} />
          {confirmReset ? (
            <>
              <button className="btn danger" onClick={() => { resetLog(); setConfirmReset(false); setMsg("History cleared."); }}>Confirm clear</button>
              <button className="btn quiet" onClick={() => setConfirmReset(false)}>Keep</button>
            </>
          ) : (
            <button className="btn quiet" onClick={() => setConfirmReset(true)} disabled={!log.length}>Clear history</button>
          )}
        </div>
      </div>
      {msg && <p className="callout" role="status" style={{ marginBottom: 16 }}>{msg}</p>}
      {log.length === 0 ? (
        <Empty title="No decisions recorded yet" action={<Link className="btn primary" to="/decisions">Open the decision workspace</Link>}>
          Approve, escalate or reject a decision in the workspace, or save a scenario in the studio. Records stay in this browser.
        </Empty>
      ) : (
        <Panel title={`${log.length} recorded decisions`} hint={`Hash chain: ${chain}`} pad={false}>
          <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
            <table className="data stack-sm">
              <thead><tr><th scope="col">When</th><th scope="col">Decision</th><th scope="col">Action</th><th scope="col">Validator</th><th scope="col">Order</th><th scope="col" className="r">Expected cost</th><th scope="col">Replay</th></tr></thead>
              <tbody>
                {log.slice().reverse().map((e) => (
                  <tr key={e.id}>
                    <td className="num small full">{new Date(e.at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</td>
                    <td className="full"><div>{e.title}</div><div className="xs faint">{e.entity}{e.note ? `. Note: ${e.note}` : ""}</div></td>
                    <td className="small" data-label="Action">{e.action}</td>
                    <td data-label="Validator"><OutcomeChip outcome={e.validator_outcome} /></td>
                    <td className="small" data-label="Order">{ordersText(e.orders)}</td>
                    <td className="r num" data-label="Expected cost">{money(e.expected_cost)}</td>
                    <td className="full"><Link to={e.action === "scenario saved" ? `/studio/${e.case_id}?${new URLSearchParams(Object.entries(e.assumptions).map(([k, v]) => [k, typeof v === "boolean" ? (v ? "1" : "0") : String(v)])).toString()}` : `/decisions/${e.case_id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <ImportCandidate />
    </>
  );
}

// ------------------------------------------------------------------ import a decision from another system

const Num = z.number().finite();
const ResourceZ = z.object({
  name: z.string().max(40), lead_days: z.number().int().min(0).max(3), unit_cost: Num.positive(), capacity: Num.min(0),
  min_quantity: Num.min(0).default(0), eligible: z.boolean().default(true), available: z.boolean().default(true),
  attributes: z.record(z.string(), z.union([Num, z.string().max(80), z.boolean()])).default({}),
});
const TermsZ = z.object({ resources: z.array(ResourceZ).length(3), budget: Num.min(0), min_commitment: Num.min(0).default(0), extra: z.record(z.string(), Num).optional() });
const EconZ = z.object({ currency: z.string().max(30).optional(), price: Num.positive(), unit_cost: Num.positive(), holding: Num.min(0), disposal: Num.min(0), goodwill: Num.min(0), shelf_life_days: z.number().int().min(1).max(10), terminal_waste_risk: Num.min(0).max(1) });
const BundleZ = z.object({
  candidate: z.object({
    decision_id: z.string().regex(/^[A-Za-z0-9_.:-]{1,120}$/),
    domain: z.literal("inventory_replenishment"),
    entity: z.object({ typical_daily_volume: Num.positive() }).passthrough(),
    data_snapshot: z.object({ age_hours: Num.min(0), history_days_missing: z.number().int().min(0).default(0), state: z.object({ on_hand_by_age: z.array(Num.min(0)).max(10), pipeline_by_day: z.array(Num.min(0)).max(8) }) }).passthrough(),
    action: z.object({ primary: Num.min(0).max(1e7), alternate: Num.min(0).max(1e7), expedite: Num.min(0).max(1e7) }),
    constraints: TermsZ,
    forecast: z.object({ levels: z.array(Num.gt(0).lt(1)).min(3).max(21), quantiles: z.array(z.array(Num.min(0))).min(1).max(4) }).passthrough().nullable(),
    financial_assumptions: EconZ,
    scenario_results: z.object({ expected_cost: Num.nullable(), n_scenarios: z.number().int().min(0).default(0) }).passthrough().nullable().optional(),
    risk_tolerance: z.object({ cvar_alpha: Num.gt(0).lt(1) }).passthrough().optional(),
  }).passthrough(),
  context: z.object({
    constraints: TermsZ, financial_assumptions: EconZ, approval_threshold: Num.min(0), max_share: z.record(z.string(), Num).default({}),
    freshness_max_age_hours: Num.positive().default(30), signals: z.record(z.string(), Num).default({}), investigation_cost: Num.min(0).default(0), review_cost: Num.min(0).default(0),
  }),
});

const econOf = (e: z.infer<typeof EconZ>) => ({ price: e.price, unit_cost: e.unit_cost, shelf_life: e.shelf_life_days, holding: e.holding, disposal: e.disposal, goodwill: e.goodwill, terminal_waste_risk: e.terminal_waste_risk });

function ImportCandidate() {
  const meta = useData<Meta>("meta");
  const [res, setRes] = useState<{ id: string; r: ValidationResult } | { error: string } | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const run = async (file?: File) => {
    if (!file || meta.status !== "ready") return;
    if (file.size > MAX_IMPORT_BYTES) return setRes({ error: "That file is larger than 1 MB." });
    let raw: unknown;
    try {
      raw = JSON.parse(await file.text());
    } catch {
      return setRes({ error: "The file is not valid JSON." });
    }
    const p = BundleZ.safeParse(raw);
    if (!p.success) return setRes({ error: `The file does not match the decision bundle format: ${p.error.issues[0]?.path.join(".")} ${p.error.issues[0]?.message}` });
    const { candidate: c, context: x } = p.data;
    const levels = c.forecast?.levels ?? [];
    const S = c.forecast ? samplePaths(c.forecast.quantiles, levels, 200, meta.data.validator_params.rho, hashSeed(c.decision_id)) : null;
    let r: ValidationResult;
    try {
      r = validateCandidate(
      {
        decision_id: c.decision_id, typical_daily_volume: c.entity.typical_daily_volume, age_hours: c.data_snapshot.age_hours,
        history_days_missing: c.data_snapshot.history_days_missing, on_hand_by_age: c.data_snapshot.state.on_hand_by_age,
        pipeline_by_day: c.data_snapshot.state.pipeline_by_day, action: c.action, plan_terms: c.constraints as never,
        plan_econ: econOf(c.financial_assumptions), forecast: c.forecast ? { levels, quantiles: c.forecast.quantiles } : null,
        claimed_expected_cost: c.scenario_results?.expected_cost ?? null, claimed_n_scenarios: c.scenario_results?.n_scenarios ?? 0,
        cvar_alpha: c.risk_tolerance?.cvar_alpha ?? 0.9,
      },
      { terms: x.constraints as never, econ: econOf(x.financial_assumptions), approval_threshold: x.approval_threshold, max_share: x.max_share,
        freshness_max_age_hours: x.freshness_max_age_hours, signals: x.signals, investigation_cost: x.investigation_cost, review_cost: x.review_cost },
      meta.data.validator_params,
      S,
    );
    } catch (e) {
      return setRes({ error: `The bundle could not be evaluated: ${(e as Error).message}` });
    }
    setRes({ id: c.decision_id, r });
  };
  return (
    <section className="section">
      <h2>Validate a decision from another system</h2>
      <p className="lede">Load a decision bundle (a candidate plus the authoritative context, schemas in <code>schemas/</code>) exported by a planning tool or the mock ERP adapter. Files stay in this browser; the limit is 1 MB. Scenarios are sampled in the browser, so figures differ slightly from the offline validator.</p>
      <div className="row">
        <button className="btn" onClick={() => ref.current?.click()} disabled={meta.status !== "ready"}>Choose a bundle file</button>
        <a className="btn quiet" href="/data/example_bundle.json" download>Download an example bundle</a>
        <input ref={ref} type="file" accept="application/json,.json" hidden onChange={(e) => run(e.target.files?.[0])} />
      </div>
      {res && ("error" in res ? <p className="callout neg" role="alert" style={{ marginTop: 12 }}>{res.error}</p> : (
        <div className="panel" style={{ marginTop: 14 }}>
          <div className="panel-pad row" style={{ justifyContent: "space-between" }}>
            <div><div className="small muted">{res.id}</div><p style={{ fontWeight: 500 }}>{res.r.reasons[0]}</p></div>
            <OutcomeChip outcome={res.r.outcome} />
          </div>
          <p className="small muted" style={{ padding: "0 20px 14px" }}>{res.r.explanation}</p>
        </div>
      ))}
    </section>
  );
}
