import { Link, useNavigate } from "react-router-dom";
import { rankCases, useCases, useData, type Loose } from "../data/load";
import { ErrorState, Loading, OutcomeChip } from "../components/ui";
import { caseLocation } from "../components/decision";
import { CATEGORY_LABEL, EVENT_LABEL, money, pct, units } from "../lib/format";

export function Overview() {
  const cases = useCases();
  const bench = useData<Loose>("benchmark");
  const dq = useData<Loose>("data_quality");
  const nav = useNavigate();
  if (cases.status === "loading") return <Loading label="Loading decisions" />;
  if (cases.status === "error") return <ErrorState message={cases.error} />;
  const ranked = rankCases(cases.data);
  const open = ranked.filter((c) => c.validation.outcome !== "recommend");
  const avoided = open.reduce((s, c) => s + Math.max(0, c.priority.cost_of_inaction), 0);
  const top = ranked[0];
  return (
    <>
      <div className="page-head">
        <div>
          <p className="briefing">
            <strong>{open.length} of {ranked.length}</strong> proposed replenishment orders need a decision before they are released.
            Leaving them unattended carries about <strong>{money(avoided)}</strong> of modeled cost over the next few days.
          </p>
          <p className="small">Orders were proposed by the expected-cost policy and checked by the independent validator. Amounts use assumed unit economics.</p>
        </div>
        {top && <Link className="btn primary" to={`/decisions/${top.id}`}>Review the top decision</Link>}
      </div>

      <section className="panel" aria-labelledby="queue-h">
        <div className="panel-head">
          <h2 id="queue-h">Decision queue</h2>
          <span className="hint">Ranked by unresolved status, then by the cost of doing nothing</span>
        </div>
        <div className="table-wrap" style={{ padding: "6px 8px 8px" }}>
          <table className="data stack-sm">
            <thead>
              <tr>
                <th scope="col">Rank</th>
                <th scope="col">Issue</th>
                <th scope="col">Validator</th>
                <th scope="col" className="r">Cost of inaction</th>
                <th scope="col">Stock cover</th>
                <th scope="col" className="r">Tail exposure</th>
                <th scope="col"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((c, i) => {
                const cover = c.priority.days_of_cover;
                return (
                  <tr key={c.id} className="clickable" onClick={() => nav(`/decisions/${c.id}`)}>
                    <td className="num faint hide-sm">{i + 1}</td>
                    <td className="full">
                      <div style={{ fontWeight: 500 }}>{c.title}</div>
                      <div className="xs faint">
                        {caseLocation(c)}, {CATEGORY_LABEL[c.entity.category] ?? c.entity.category}
                        {c.events.length > 0 && <>, {c.events.map((e) => EVENT_LABEL[e] ?? e).join(" and ").toLowerCase()}</>}
                      </div>
                    </td>
                    <td data-label="Validator"><OutcomeChip outcome={c.validation.outcome} /></td>
                    <td className="r num" data-label="Cost of inaction">{money(c.priority.cost_of_inaction)}</td>
                    <td data-label="Stock cover">
                      <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                        <div className={`coverbar${cover < 1 ? " low" : ""}`} aria-hidden="true"><span style={{ width: `${Math.min(100, (cover / 3) * 100)}%` }} /></div>
                        <span className="num small">{units(cover)} d</span>
                      </div>
                    </td>
                    <td className="r num" data-label="Tail exposure">{money(c.priority.downside)}</td>
                    <td className="r full"><Link to={`/decisions/${c.id}`} onClick={(e) => e.stopPropagation()}>Open<span className="sr-only"> {c.title}</span></Link></td>
                  </tr>
                );
              })}
            </tbody>
            <caption>Cost of inaction: expected cost of placing no order minus the best order on the evaluation grid. Tail exposure: average of the worst 10% of scenarios minus the expected cost of the recommended order.</caption>
          </table>
        </div>
      </section>

      <div className="grid-2e section">
        <section className="panel panel-pad" aria-labelledby="find-h">
          <h2 id="find-h" style={{ fontSize: "var(--fs-md)", marginBottom: 10 }}>What the benchmark found</h2>
          {bench.status === "ready" ? <Findings bench={bench.data} /> : bench.status === "error" ? <p className="muted">{bench.error}</p> : <div className="skeleton" style={{ height: 120 }} />}
          <p style={{ marginTop: 12 }}><Link to="/benchmark">See the full benchmark</Link></p>
        </section>
        <section className="panel panel-pad" aria-labelledby="data-h">
          <h2 id="data-h" style={{ fontSize: "var(--fs-md)", marginBottom: 10 }}>Data behind these decisions</h2>
          {dq.status === "ready" ? (
            <dl className="kv">
              <dt>Source</dt><dd>{dq.data.data_source === "synthetic_fixture" ? "Synthetic fixture, real schema" : "FreshRetailNet-50K"}</dd>
              <dt>Coverage</dt><dd className="num">{dq.data.n_series} store-products, {dq.data.n_days} days</dd>
              <dt>Dates</dt><dd className="num">{dq.data.date_range[0]} to {dq.data.date_range[1]}</dd>
              <dt>Rows quarantined</dt><dd className="num">{dq.data.rows_quarantined} of {dq.data.rows_raw}</dd>
              <dt>Suppliers, costs, disruptions</dt><dd>Simulated</dd>
            </dl>
          ) : <div className="skeleton" style={{ height: 120 }} />}
          <p style={{ marginTop: 12 }}><Link to="/data">Check data reliability</Link></p>
        </section>
      </div>
    </>
  );
}

const MODEL_NAME: Record<string, string> = {
  seasonal_naive: "seasonal naive", moving_average: "moving average", lgbm_point: "LightGBM point forecast",
  lgbm_quantile_observed: "quantiles on observed sales", lgbm_quantile_recovered: "stockout-aware quantiles",
  lgbm_quantile_recovered_nopromo: "stockout-aware quantiles without promotions",
};
/** Plain-language effect of a paired comparison; "no clear effect" whenever the 95% interval spans zero. */
const effect = (p: Loose) =>
  p.relative_lo <= 0 && p.relative_hi >= 0
    ? "had no clear effect on total cost"
    : `${p.relative_diff > 0 ? "raised" : "lowered"} total cost by ${Math.abs(100 * p.relative_diff).toFixed(1)}%`;

function Findings({ bench }: { bench: Loose }) {
  const pu = bench.paired?.unreliable?.P5a_vs_P3;
  const pn = bench.paired?.normal?.P5a_vs_P3;
  const mu = bench.main?.unreliable;
  const h1 = (bench.hypotheses as Loose[]).find((h) => h.id === "H1");
  return (
    <ul className="small" style={{ paddingLeft: 18, margin: 0, display: "grid", gap: 8 }}>
      {mu && (
        <li>
          With unreliable data, the validator cut unsafe executed orders from {pct(mu.P3.unsafe_executed_rate ?? 0, 2)} to {pct(mu.P5a.unsafe_executed_rate ?? 0, 2)} and hard-constraint
          breaches from {mu.P3.hard_violations} to {mu.P5a.hard_violations}.
        </li>
      )}
      {pu && pn && (
        <li>
          Counting review and stock-count costs, validation {effect(pu)} with unreliable data and {effect(pn)} in normal operations (paired comparison, 95% intervals).
          The simulator does not charge for a breach itself, only for the shortage when a breached order is cut back, so this understates what breaches cost in practice.
        </li>
      )}
      {h1 && h1.evidence.best_accuracy_model !== h1.evidence.best_cost_model && <li>The most accurate forecast on observed sales ({MODEL_NAME[h1.evidence.best_accuracy_model] ?? h1.evidence.best_accuracy_model}) did not produce the cheapest decisions; {MODEL_NAME[h1.evidence.best_cost_model] ?? h1.evidence.best_cost_model} did.</li>}
    </ul>
  );
}
