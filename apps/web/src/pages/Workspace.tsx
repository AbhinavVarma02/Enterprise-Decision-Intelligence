import { useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { rankCases, useCases } from "../data/load";
import { ErrorState, GateLedger, Loading, NotFound, OutcomeChip, Panel } from "../components/ui";
import { AlternativesTable, TermsTable, caseLocation, ordersText } from "../components/decision";
import { FanChart, InventoryBars } from "../components/charts";
import { alternatives as evalAlternatives } from "../engine/inaction";
import { modifiedSupply } from "../engine/studio";
import { append } from "../state/history";
import type { DecisionCase } from "../engine/types";
import type { Entry } from "../state/history";
import { CATEGORY_LABEL, EVENT_LABEL, OUTCOME_HEADLINE, money, pct, units } from "../lib/format";

function addDays(date: string, n: number): string {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function Workspace() {
  const { caseId } = useParams();
  const cases = useCases();
  if (cases.status === "loading") return <Loading label="Loading decision" />;
  if (cases.status === "error") return <ErrorState message={cases.error} />;
  const ranked = rankCases(cases.data);
  if (!caseId) return ranked.length ? <Navigate to={`/decisions/${ranked[0].id}`} replace /> : <NotFound />;
  const c = ranked.find((x) => x.id === caseId);
  if (!c) return <NotFound />;
  return <Dossier key={c.id} c={c} all={ranked} />;
}

function Dossier({ c, all }: { c: DecisionCase; all: DecisionCase[] }) {
  const nav = useNavigate();
  const v = c.validation;
  const [selected, setSelected] = useState("act_now");
  const [note, setNote] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const suggested = useMemo(
    () => (v.recommended_action ? [v.recommended_action.primary ?? 0, v.recommended_action.alternate ?? 0, v.recommended_action.expedite ?? 0] : null),
    [v.recommended_action],
  );
  const options = useMemo(() => {
    if (!suggested) return c.alternatives;
    const sup = modifiedSupply(c, {});
    const S = c.scenarios.map((r) => r.slice(0, c.horizon_days));
    const row = evalAlternatives(suggested, c.state.recorded_on_hand_by_age, c.state.pipeline_by_day, sup, c.economics, S, c.review_cost, 0.9, c.revenue_scale)[0];
    const suggestion = { ...row, key: "suggested", label: "Validator's suggestion", delta_vs_act_now: row.expected_cost - c.alternatives[0].expected_cost };
    return [...c.alternatives.slice(0, 1), suggestion, ...c.alternatives.slice(1)];
  }, [c, suggested]);
  const alt = options.find((a) => a.key === selected) ?? options[0];
  const act = options[0];
  const dates = c.fan.map((_, i) => (i === 0 ? "Today" : addDays(c.date, i)));
  const ageLabels = c.state.recorded_on_hand_by_age.map((_, i) => (i === 0 ? "arrived today" : `${i} d old`));
  const onHand = c.state.recorded_on_hand_by_age.reduce((s, x) => s + x, 0);
  const missing = v.gates.filter((g) => (g.gate === "G6" || g.gate === "G1") && g.status !== "pass");

  const record = async (action: Entry["action"], orders: number[]) => {
    await append({
      case_id: c.id,
      title: c.title,
      entity: caseLocation(c),
      action,
      validator_outcome: v.outcome,
      orders,
      expected_cost: action === "approved" ? alt.expected_cost : (v.metrics.expected_cost ?? null),
      cvar: action === "approved" ? alt.cvar : (v.metrics.cvar ?? null),
      assumptions: {},
      note: note.slice(0, 500),
    });
    setToast(`Recorded: ${action}. This is a simulated approval; no order was sent.`);
    setNote("");
    window.setTimeout(() => setToast(null), 4000);
  };

  const sortedOptions = useMemo(() => all.map((x) => ({ id: x.id, label: `${x.title} (${caseLocation(x)})` })), [all]);

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 18 }}>
        <label className="row small" style={{ gap: 8 }}>
          <span className="muted">Decision</span>
          <select className="select" value={c.id} onChange={(e) => nav(`/decisions/${e.target.value}`)} aria-label="Choose a decision">
            {sortedOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </label>
        <div className="row small">
          <span className="tag">{caseLocation(c)}</span>
          <span className="tag">{CATEGORY_LABEL[c.entity.category] ?? c.entity.category}</span>
          <span className="tag num">Day {c.day}, {c.date}</span>
          {c.events.map((e) => <span key={e} className="tag">{EVENT_LABEL[e] ?? e}</span>)}
        </div>
      </div>

      <section className="verdict" aria-labelledby="verdict-h">
        <span className={`bar o-${v.outcome}`} aria-hidden="true" />
        <div>
          <div className="row" style={{ marginBottom: 6 }}>
            <OutcomeChip outcome={v.outcome} />
            <span className="small muted">{c.title}</span>
          </div>
          <h1 id="verdict-h">{OUTCOME_HEADLINE[v.outcome]}</h1>
          <p className="why">{v.outcome === "reject" ? `The proposal breaks a hard constraint: ${v.reasons[0].replace(/\.$/, "")}.` : v.reasons[0]}</p>
          <p className="small faint" style={{ marginTop: 6, maxWidth: "88ch" }}>{v.explanation}</p>
        </div>
      </section>

      <div className="grid-2 section">
        <div className="stack">
          <Panel title="Options and their consequences" hint={`${c.scenarios.length} demand scenarios over ${c.horizon_days} days`} pad={false} id="opts-h">
            <div style={{ padding: "4px 8px 6px" }}>
              <AlternativesTable alts={options} selected={selected} onSelect={setSelected} proposed={c.candidate.orders}
                caption="Spread: blue dot is expected cost, grey tick the 90th percentile, red tick the average of the worst 10% of scenarios." />
            </div>
            <div className="panel-pad" style={{ borderTop: "1px solid var(--line-2)" }} aria-live="polite">
              <h3 style={{ fontSize: "var(--fs-md)" }}>{alt.label}: {ordersText(alt.orders)}{alt.key !== "suggested" && alt.key !== "smaller" && alt.key !== "no_action" && c.candidate.orders.some((q, i) => q > alt.orders[i] + 1e-6) ? " can be delivered" : ""}</h3>
              <p className="small muted" style={{ marginTop: 4 }}>
                {alt.key === "act_now"
                  ? `Expected cost ${money(alt.expected_cost)} over ${c.horizon_days} days with ${pct(alt.expected_fill_rate)} of demand served. In ${pct(alt.prob_over_tolerance ?? 0, 0)} of scenarios cost runs more than a day of revenue above that.`
                  : `Compared with acting now, expected cost ${alt.delta_vs_act_now >= 0 ? "rises" : "falls"} by ${money(Math.abs(alt.delta_vs_act_now))}, fill rate moves from ${pct(act.expected_fill_rate)} to ${pct(alt.expected_fill_rate)}, and the worst-10% average is ${money(alt.cvar)}.`}
                {alt.governance_cost > 0 && ` Includes ${money(alt.governance_cost)} of review time.`}
              </p>
            </div>
          </Panel>
          <div className="grid-2e">
            <Panel title="Demand outlook" hint={c.forecast.staleness_days ? `Built on data ${c.forecast.staleness_days} days old` : "Calibrated quantile forecast"}>
              <FanChart fan={c.fan} dates={dates} onHand={onHand} />
            </Panel>
            <Panel title="Stock on hand" hint={`Typical demand ${units(c.mu)} units a day`}>
              <InventoryBars recorded={c.state.recorded_on_hand_by_age} verified={c.state.verified_on_hand_by_age} labels={ageLabels} />
              <p className="xs faint" style={{ marginTop: 6 }}>
                Shelf life {c.economics.shelf_life} days. Inbound: {c.state.pipeline_by_day.slice(1).map((x, i) => `${units(x)} on day +${i + 1}`).join(", ")}.
              </p>
            </Panel>
          </div>
          <Panel title="Supplier terms" pad={false}>
            <div style={{ padding: "4px 8px 8px" }}><TermsTable plan={c.plan_terms} current={c.current_terms} /></div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="Validation gates" hint="Independent of the policy that proposed the order" pad={false}>
            <GateLedger gates={v.gates} />
          </Panel>
          <Panel title="What to verify before committing">
            {v.value_of_information ? (
              <div className="small">
                <p>Verifying <strong>{v.value_of_information.input}</strong> is worth about <strong className="num">{money(v.value_of_information.value_vs_candidate)}</strong> against
                  this order, and up to <span className="num">{money(v.value_of_information.evpi)}</span> against the best hedged order (EVPI). A cycle count costs <span className="num">{money(v.value_of_information.investigation_cost)}</span>.</p>
                <table className="data" style={{ marginTop: 10 }}>
                  <thead><tr><th scope="col">If the true state is</th><th scope="col" className="r">Prior</th></tr></thead>
                  <tbody>{v.value_of_information.labels.map((l, i) => <tr key={l}><td>{l}</td><td className="r num">{pct(v.value_of_information!.probabilities[i], 0)}</td></tr>)}</tbody>
                </table>
              </div>
            ) : missing.length ? (
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{missing.map((g) => <li key={g.gate}>{g.summary}</li>)}</ul>
            ) : (
              <p className="small muted">Nothing material is missing. Inventory, sales history and supplier terms passed their checks.</p>
            )}
          </Panel>
          <Panel title="Decide" hint="Simulated: no order or message leaves this browser">
            <div className="stack" style={{ gap: 12 }}>
              <label className="field">
                <span className="small">Note for the record (optional)</span>
                <textarea className="text" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} style={{ resize: "vertical", border: "1px solid var(--line)", borderRadius: 8, padding: 8 }} />
              </label>
              <div className="row">
                <button className="btn primary" onClick={() => record("approved", alt.orders)} disabled={v.outcome === "reject" && selected === "act_now"}>
                  Approve {selected === "act_now" ? "proposed order" : alt.label.toLowerCase()}
                </button>
                {suggested && (
                  <button className="btn" onClick={() => record("approved", suggested)}>Approve suggested alternative</button>
                )}
                <button className="btn" onClick={() => record("count requested", [0, 0, 0])}>Request cycle count</button>
                <button className="btn" onClick={() => record("escalated", c.candidate.orders)}>Escalate</button>
                <button className="btn danger" onClick={() => record("rejected", [0, 0, 0])}>Reject</button>
              </div>
              {v.outcome === "reject" && <p className="xs faint">The proposed order breaks a hard constraint, so it cannot be approved as is. Choose another option or the suggested alternative.</p>}
              <p className="xs faint">Approval threshold {money(c.approval_threshold)}. Decisions are written to the <Link to="/history">decision history</Link> in this browser only.</p>
            </div>
          </Panel>
          <p className="small"><Link to={`/studio/${c.id}`}>Change assumptions for this decision in the scenario studio</Link></p>
        </div>
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </>
  );
}
