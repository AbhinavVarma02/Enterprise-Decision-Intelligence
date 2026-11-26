import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useData, type Loose } from "../data/load";
import { ErrorState, Loading, OutcomeChip, Panel } from "../components/ui";
import { DotWhisker, LineSeries, Scatter, type DotRow } from "../components/charts";
import { POLICY_LABEL, money, pct, titleCase } from "../lib/format";

const CONDITIONS = [
  { key: "normal", label: "Normal operations" },
  { key: "unreliable", label: "Unreliable data" },
  { key: "disruption", label: "Held-out disruptions" },
];
const SHORT_MODEL: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  lgbm_point: "LightGBM point",
  lgbm_quantile_observed: "Quantiles, observed sales",
  lgbm_quantile_recovered: "Quantiles, stockout-aware",
  lgbm_quantile_recovered_nopromo: "Stockout-aware, no promo",
};
const ABLATION_LABEL: Record<string, string> = {
  P5a_no_stockout_aware: "Validator without stockout-aware forecasts",
  P5a_no_voi: "Validator without value of information",
  P5a_no_escalation: "Validator without escalation",
  P5a_no_risk_review: "Validator without risk review",
  P5a_untuned: "Validator with untuned thresholds",
  P3_obs_vs_P3: "P3 on observed-sales forecasts (vs P3)",
  no_validation_P3_vs_P5a: "P3 without any validation",
};
const POLICIES = ["P1", "P2", "P3", "P4", "P5a", "P5b", "ORACLE"];

function verdictClass(v: string): string {
  return v.startsWith("supported") ? "v-supported" : v.startsWith("partially") ? "v-partially" : "v-not";
}

function hypothesisLine(h: Loose): string {
  const e = h.evidence;
  switch (h.id) {
    case "H1": {
      const d = e.paired_cost_difference?.diff_cost_per_day;
      return `Best on observed-sales accuracy: ${SHORT_MODEL[e.best_accuracy_model] ?? e.best_accuracy_model}. Lowest decision cost: ${SHORT_MODEL[e.best_cost_model] ?? e.best_cost_model}${d ? ` (difference ${money(d.mean)} per day, 95% CI ${money(d.lo)} to ${money(d.hi)})` : ""}. Rank agreement (Kendall tau) ${e.kendall_tau_observed?.toFixed(2)} against observed sales${e.kendall_tau_latent !== null && e.kendall_tau_latent !== undefined ? `, ${e.kendall_tau_latent.toFixed(2)} against true demand` : ""}.`;
    }
    case "H2":
      return `Unsafe decisions ${pct(e.unsafe_P3, 2)} without validation, ${pct(e.unsafe_P5a, 2)} with it. Net cost change ${pct(e.paired?.relative_diff, 1, true)} (95% CI ${pct(e.paired?.relative_lo, 1, true)} to ${pct(e.paired?.relative_hi, 1, true)}).`;
    case "H3":
      return `Net cost change in normal operations ${pct(e.paired?.relative_diff, 1, true)} (95% CI ${pct(e.paired?.relative_lo, 1, true)} to ${pct(e.paired?.relative_hi, 1, true)}); the target band was plus or minus 2%.`;
    case "H4":
      return CONDITIONS.map((c) => `${c.label.toLowerCase()}: tail ${money(e[c.key].cvar90_P4)} vs ${money(e[c.key].cvar90_P3)}, mean ${money(e[c.key].mean_P4)} vs ${money(e[c.key].mean_P3)}`).join("; ") + ".";
    case "H5":
      return `On artificially censored in-stock days, bias moved from ${e.observed_as_demand.bias_pct.toFixed(1)}% to ${e.profile_recovery.bias_pct.toFixed(1)}% and mean absolute error from ${e.observed_as_demand.mae.toFixed(2)} to ${e.profile_recovery.mae.toFixed(2)} units.`;
    default:
      return "";
  }
}

export function Benchmark() {
  const b = useData<Loose>("benchmark");
  const sec = useData<Loose>("secondary");
  const evidence = useData<Loose>("research_evidence");
  const [params, setParams] = useSearchParams();
  const [cond, setCond] = useState("unreliable");
  if (b.status === "loading" || evidence.status === "loading") return <Loading label="Loading benchmark" />;
  if (b.status === "error") return <ErrorState message={b.error} />;
  const research = evidence.status === "ready" ? evidence.data : null;
  const retail = Boolean(research && params.get("study") !== "synthetic");
  const d = retail ? research.retail_benchmark : b.data;
  const meta = d.meta;
  const main = d.main[cond];
  const economics = retail ? research.retail_economics : research?.synthetic_economics;
  const rows: DotRow[] = POLICIES.filter((p) => p !== "P3" && d.paired[cond][`${p}_vs_P3`]?.diff_cost_per_day).map((p) => {
    const ci = d.paired[cond][`${p}_vs_P3`].diff_cost_per_day;
    return { label: `${p} ${POLICY_LABEL[p]}`, mean: ci.mean, lo: ci.lo, hi: ci.hi, emphasis: p.startsWith("P5") ? "ours" : p === "ORACLE" ? "oracle" : undefined };
  });
  const abl = d.ablations[cond];
  const ablRows: DotRow[] = Object.entries(abl as Record<string, Loose>).filter(([, v]) => v && v.diff_cost_per_day).map(([k, v]) => ({
    label: ABLATION_LABEL[k] ?? k.replace(/_/g, " "),
    mean: v.diff_cost_per_day.mean, lo: v.diff_cost_per_day.lo, hi: v.diff_cost_per_day.hi,
  }));
  const rc = (d.risk_coverage as Loose[]).filter((x) => x.include_approval_routing && x.threshold_scale !== "hard rules only");
  const rcNo = (d.risk_coverage as Loose[]).filter((x) => !x.include_approval_routing && x.threshold_scale !== "hard rules only");
  const fv = d.forecast_variants as Loose[];
  const points = fv.flatMap((r) => {
    const base = { label: SHORT_MODEL[r.model] ?? r.model.replace(/_/g, " "), y: r.decision_cost_per_day.mean, highlight: r.model === "lgbm_quantile_recovered" };
    const out = [{ ...base, x: r.pinball_vs_observed }];
    return out;
  });
  const tuned = meta.tuning?.validator_soft_scale;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Decision Reliability Benchmark</h1>
          <p>
            {meta.n_series} store-products, {meta.realizations} matched realizations per condition, final test on days {meta.window[0]} to {meta.window[1]} (the official evaluation split), {meta.n_decisions.toLocaleString("en-US")} simulated decisions.
            Every policy faces identical demand, faults and disruptions. Intervals are 95% cluster-bootstrap intervals over store-products.
          </p>
        </div>
        <a className="btn" href={retail ? "/data/research_evidence.json" : "/data/benchmark.json"} download>Download results JSON</a>
      </div>
      <div className="study-switch">
        {research && <div className="segmented" role="group" aria-label="Retail study">
          <button aria-pressed={retail} onClick={() => setParams({ study: "retail" }, { replace: true })}>FreshRetailNet pilot</button>
          <button aria-pressed={!retail} onClick={() => setParams({ study: "synthetic" }, { replace: true })}>Synthetic benchmark</button>
        </div>}
        <p className="small muted">
          {retail ? "Observed sales and stockout flags · Estimated demand during stockouts · Simulated suppliers and assumed costs"
            : "Controlled synthetic fixture · Generated demand, supplier terms and faults · Assumed costs"}
        </p>
        {evidence.status === "error" && <p className="small muted">The FreshRetailNet pilot is unavailable in this build.</p>}
      </div>

      {economics && <ValidationTradeOff economics={economics} detection={d.detection.unreliable.P5a} />}

      <Panel title="Hypotheses and verdicts" hint="Rules fixed in the protocol before results were read" pad={false}>
        <div>
          {(d.hypotheses as Loose[]).map((h) => (
            <div className="hyp" key={h.id}>
              <span className="hid">{h.id}</span>
              <div>
                <div style={{ fontWeight: 500 }}>{h.statement}</div>
                <div className="small muted" style={{ marginTop: 3 }}>{hypothesisLine(h)}</div>
              </div>
              <span className={`chip ${verdictClass(h.verdict)}`}>{titleCase(h.verdict)}</span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="section row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ fontSize: "var(--fs-lg)" }}>Policy comparison</h2>
        <div className="segmented" role="group" aria-label="Condition">
          {CONDITIONS.map((c) => <button key={c.key} aria-pressed={cond === c.key} onClick={() => setCond(c.key)}>{c.label}</button>)}
        </div>
      </div>
      <div className="grid-2" style={{ marginTop: 14 }}>
        <Panel title="Cost per store-product day versus P3" hint="Paired difference; left of the line is cheaper">
          {rows.length ? <DotWhisker rows={rows} refValue={0} format={(v) => money(v, { signed: true })} ariaLabel={`Paired cost difference versus P3 by policy, ${cond}`} /> : <p className="small muted">Paired results are not available for this run.</p>}
          <p className="xs faint">P3 averages {money(main.P3.cost_per_series_day.mean)} per store-product day here. Differences include review and count costs.</p>
        </Panel>
        <Panel title="Effect of the validation layer" hint="Paired, same worlds">
          <table className="data">
            <thead><tr><th scope="col">Condition</th><th scope="col" className="r">P5a vs P3</th><th scope="col" className="r">P5b vs P4</th></tr></thead>
            <tbody>
              {CONDITIONS.map((c) => {
                const a = d.paired[c.key].P5a_vs_P3;
                const bb = d.paired[c.key].P5b_vs_P4;
                return (
                  <tr key={c.key}>
                    <td>{c.label}</td>
                    <td className="r num">{pct(a.relative_diff, 1, true)}<div className="xs faint">{pct(a.relative_lo, 1, true)} to {pct(a.relative_hi, 1, true)}</div></td>
                    <td className="r num">{pct(bb.relative_diff, 1, true)}<div className="xs faint">{pct(bb.relative_lo, 1, true)} to {pct(bb.relative_hi, 1, true)}</div></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="xs faint" style={{ marginTop: 8 }}>Positive means the validated policy cost more. Validator soft thresholds were tuned on days 77 to 90{tuned ? ` (scale ${tuned >= 1e5 ? "off" : tuned})` : ""}.</p>
        </Panel>
      </div>

      <Panel title={`Detail: ${CONDITIONS.find((c) => c.key === cond)?.label.toLowerCase()}`} pad={false}>
        <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
          <table className="data stack-sm stack-md">
            <thead>
              <tr>
                <th scope="col">Policy</th><th scope="col" className="r">Cost per day</th><th scope="col" className="r">Tail (CVaR90)</th>
                <th scope="col" className="r">Fill rate</th><th scope="col" className="r">Waste</th><th scope="col" className="r">Governance per day</th>
                <th scope="col" className="r">Unsafe decisions</th><th scope="col" className="r">Constraint breaches</th><th scope="col">Validator outcomes</th>
              </tr>
            </thead>
            <tbody>
              {POLICIES.filter((p) => main[p]).map((p) => {
                const m = main[p];
                return (
                  <tr key={p}>
                    <td className="full"><strong>{p}</strong> <span className="small muted">{POLICY_LABEL[p]}</span></td>
                    <td className="r num" data-label="Cost per day">{money(m.cost_per_series_day.mean)}</td>
                    <td className="r num" data-label="Tail (CVaR90)">{money(m.cvar90_series_cost_per_day)}</td>
                    <td className="r num" data-label="Fill rate">{pct(m.fill_rate)}</td>
                    <td className="r num" data-label="Waste">{pct(m.waste_rate)}</td>
                    <td className="r num" data-label="Governance per day">{money(m.governance_cost_per_day)}</td>
                    <td className="r num" data-label="Unsafe decisions">{m.unsafe_executed_rate == null ? "n/a" : pct(m.unsafe_executed_rate, 2)}</td>
                    <td className="r num" data-label="Constraint breaches">{m.hard_violations ?? 0}</td>
                    <td className="full">{p.startsWith("P5") ? <div className="row" style={{ gap: 4 }}>{Object.entries(m.outcomes as Record<string, number>).map(([o, n]) => <span key={o} className="row" style={{ gap: 3 }}><OutcomeChip outcome={o} /><span className="xs num">{n}</span></span>)}</div> : <span className="xs faint">executes every order</span>}</td>
                  </tr>
                );
              })}
            </tbody>
            <caption>Unsafe decisions use all store-product decision days, including days with no order. A decision is unsafe if it breaches a hard constraint or its expected regret exceeds half a day of revenue. A submission can breach more than one constraint. The oracle is a rolling hindsight reference.</caption>
          </table>
        </div>
      </Panel>

      <div className="grid-2e section">
        <Panel title="Coverage versus intervention thresholds" hint="Validated decisions, all conditions">
          <LineSeries
            series={[
              { name: "Automatic coverage, approvals routed", color: "#2742c4", points: rc.map((x) => ({ x: Math.log2(x.threshold_scale), y: x.coverage })) },
              { name: "Coverage without approval routing", color: "#6a3fb5", dashed: true, points: rcNo.map((x) => ({ x: Math.log2(x.threshold_scale), y: x.coverage })) },
              { name: "Unsafe candidates caught", color: "#b3261e", points: rc.map((x) => ({ x: Math.log2(x.threshold_scale), y: x.unsafe_caught })) },
            ]}
            xLabel="Soft threshold scale (log2; right = more permissive)" yLabel="Share" ariaLabel="Coverage and unsafe detection by threshold scale"
            xFormat={(v) => `${(2 ** v).toFixed(v < 0 ? 2 : 0)}x`} yFormat={(v) => pct(v, 0)}
          />
          <p className="xs faint">Hard rules (constraint breaches, stale or missing evidence) stay on at every scale. Recomputed from stored gate evidence, without re-simulating outcomes.</p>
        </Panel>
        <Panel title="Ablations against full validation" hint="Cost per day difference vs P5a">
          {ablRows.length ? <DotWhisker rows={ablRows} ariaLabel="Ablation cost differences" refValue={0} format={(v) => money(v, { signed: true })} /> : <p className="muted small">No ablations for this condition.</p>}
        </Panel>
      </div>

      <div className="grid-2e section">
        <Panel title="Forecast accuracy versus decision cost" hint="Same optimizer, normal operations">
          <Scatter points={points} xLabel="Pinball loss against observed sales (lower = more accurate)" xLabelShort="Pinball loss vs observed sales (lower is better)" yLabel="Decision cost per day"
            ariaLabel="Forecast accuracy against decision cost by model" />
          <p className="xs faint">Observed sales are censored by stockouts, so accuracy measured against them rewards forecasts that under-predict demand.</p>
        </Panel>
        <Panel title="External recommendation audit" hint="Faults injected into benchmark candidates" pad={false}>
          <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
            <table className="data stack-sm">
              <thead><tr><th scope="col">Injected fault</th><th scope="col" className="r">Unsafe</th><th scope="col" className="r">Flagged</th><th scope="col" className="r">Unsafe caught</th></tr></thead>
              <tbody>
                {Object.entries(d.audit.by_fault as Record<string, Loose>).map(([k, v]) => (
                  <tr key={k}><td className="full" style={{ fontWeight: 500 }}>{titleCase(k)}</td><td className="r num" data-label="Unsafe">{pct(v.unsafe_share, 0)}</td><td className="r num" data-label="Flagged">{pct(v.flagged_share, 0)}</td><td className="r num" data-label="Unsafe caught">{v.unsafe_share > 0 ? pct(v.recall_on_unsafe, 0) : "n/a"}</td></tr>
                ))}
              </tbody>
              <caption>{d.audit.n_evaluations} validations of {d.audit.n_base_candidates} candidates. Overall: {pct(d.audit.overall_recall_on_unsafe, 0)} of unsafe candidates flagged; {pct(d.audit.false_alarm_rate_on_safe, 0)} of safe ones flagged too. Flagging a safe but inconsistent candidate (for example a misreported cost) is intended.</caption>
            </table>
          </div>
        </Panel>
      </div>

      {retail && research.selective_validation && <SelectiveReview experiment={research.selective_validation} />}

      <div className="grid-2e section">
        <Panel title="Sensitivity: validation over P3 with unreliable data" pad={false}>
          <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
            <table className="data">
              <thead><tr><th scope="col">Assumption changed</th><th scope="col" className="r">Cost change</th><th scope="col" className="r">95% CI</th></tr></thead>
              <tbody>
                {(d.sensitivity as Loose[]).map((s) => (
                  <tr key={s.setting}><td>{s.setting.replace(/_/g, " ").replace("x", "times ")}</td><td className="r num">{pct(s.P5a_vs_P3.relative_diff, 1, true)}</td><td className="r num xs">{pct(s.P5a_vs_P3.relative_lo, 1, true)} to {pct(s.P5a_vs_P3.relative_hi, 1, true)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="Second domain: cloud capacity reservation" hint="Synthetic; same contract and validator">
          {sec.status === "ready" ? <Secondary s={sec.data} /> : sec.status === "error" ? <p className="small muted">Secondary-domain results are not available in this build.</p> : <div className="skeleton" style={{ height: 160 }} />}
        </Panel>
      </div>

      <div className="callout section" style={{ marginTop: 28 }}>
        Read with care: costs use assumed economics; suppliers, faults and disruptions are simulated; the test window is seven days; the oracle is a hindsight bound. Methods and limitations are on the <Link to="/methodology">methodology</Link> page.
      </div>
    </>
  );
}

function ValidationTradeOff({ economics, detection }: { economics: Loose; detection: Loose }) {
  const [breachCost, setBreachCost] = useState(10);
  const avoided = economics.baseline_breached_submissions - economics.validated_breached_submissions;
  const delta = economics.base_delta_per_day - breachCost * avoided / economics.decision_days_per_policy;
  return <Panel title="The cost of safer decisions" hint="P5a versus P3 under unreliable data">
    <div className="validation-economics">
      <dl className="validation-ledger">
        <div><dt>Unsafe proposals intercepted</dt><dd>{detection.n_unsafe_intercepted ?? detection.n_unsafe} of {detection.n_candidates.toLocaleString("en-US")}</dd></div>
        <div><dt>Submissions with hard breaches</dt><dd>{economics.baseline_breached_submissions} → {economics.validated_breached_submissions}</dd></div>
        <div><dt>Base cost change per day</dt><dd>{money(economics.base_delta_per_day, { signed: true })}</dd></div>
      </dl>
      <div className="breach-scenario">
        <div className="row breach-label"><label htmlFor="breach-cost">Additional cost per breached submission</label><strong className="num">{money(breachCost)}</strong></div>
        <input id="breach-cost" type="range" min={0} max={50} step={0.25} value={breachCost} onChange={(e) => setBreachCost(e.currentTarget.valueAsNumber)} aria-valuetext={money(breachCost)} />
        <p className="breach-total" aria-live="polite"><strong className="num">{money(delta, { signed: true })}</strong> net validation cost per store-product day</p>
        <p className="small muted">{economics.break_even_per_breached_submission === null ? "This comparison has no positive count of avoided submissions." : `Break-even is ${money(economics.break_even_per_breached_submission)} per breached submission.`} Apply only costs beyond procurement, expediting and shortages already charged by the simulator.</p>
      </div>
    </div>
  </Panel>;
}

function SelectiveReview({ experiment }: { experiment: Loose }) {
  return <Panel title="Selective review in fresh simulated scenarios" hint="Required checks and approvals stay active">
    <div className="table-wrap">
      <table className="data stack-sm">
        <thead><tr><th scope="col">Condition</th><th scope="col" className="r">Governance per day</th><th scope="col" className="r">Unsafe decisions</th><th scope="col" className="r">Total cost change</th></tr></thead>
        <tbody>{CONDITIONS.map(({ key, label }) => {
          const result = experiment.conditions[key];
          const a = result.policies.P5a;
          const b = result.policies.P5a_selective;
          const pair = result.paired_selective_vs_p5a;
          return <tr key={key}>
            <th scope="row">{label}</th>
            <td className="r num" data-label="Governance per day">{money(a.governance_cost_per_day)} → {money(b.governance_cost_per_day)}</td>
            <td className="r num" data-label="Unsafe decisions">{a.unsafe_executed_decisions} → {b.unsafe_executed_decisions}</td>
            <td className="r num" data-label="Total cost change">{pct(pair.relative_diff, 2, true)}<div className="xs muted">{pct(pair.relative_lo, 2, true)} to {pct(pair.relative_hi, 2, true)}</div></td>
          </tr>;
        })}</tbody>
        <caption>Full to selective validation on the same retail series and evaluation dates, with a fresh seed for simulated worlds.</caption>
      </table>
    </div>
  </Panel>;
}

function Secondary({ s }: { s: Loose }) {
  const conds = ["normal", "unreliable", "disruption"];
  const pols = ["C1_reserve_mean", "C2_deterministic", "C3_expected", "C4_cvar", "C5_validated"];
  return (
    <>
      <div className="table-wrap">
        <table className="data stack-sm">
          <thead><tr><th scope="col">Policy</th>{conds.map((c) => <th key={c} scope="col" className="r">{titleCase(c)}</th>)}</tr></thead>
          <tbody>
            {pols.map((p) => (
              <tr key={p}><td className="full" style={{ fontWeight: 500 }}>{p.replace(/_/g, " ")}</td>{conds.map((c) => <td key={c} className="r num" data-label={titleCase(c)}>{money(s.results[c]?.[p]?.cost_per_service_day?.mean)}</td>)}</tr>
            ))}
          </tbody>
          <caption>Cost per service-day. {s.reuse?.engine_change_needed ? `Engine change needed: ${s.reuse.engine_change_needed}.` : ""}</caption>
        </table>
      </div>
    </>
  );
}
