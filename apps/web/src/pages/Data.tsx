import { Link } from "react-router-dom";
import { useData, type Loose } from "../data/load";
import { ErrorState, Loading, Panel } from "../components/ui";
import { DailySeries } from "../components/charts";
import { pct, titleCase, units } from "../lib/format";

const REGISTER = [
  { item: "Daily and hourly sales", kind: "Observed", note: "Normalized by the publisher; rescaled by one global factor in this project." },
  { item: "Hourly stock-out flags", kind: "Observed", note: "Meaning of the flag inferred from consistency with the out-of-stock hour count; checked on load." },
  { item: "Demand during stock-outs", kind: "Estimated", note: "Hourly-profile recovery. Sensitivity uses observed sales and an uplift case for unobserved demand." },
  { item: "Forecast quantiles", kind: "Estimated", note: "LightGBM quantile models with split-conformal calibration; fitted on earlier days only." },
  { item: "Inventory on hand and in transit", kind: "Simulated", note: "Perishable FIFO simulator; starts each window at one day of typical demand." },
  { item: "Suppliers, lead times, capacities, budgets", kind: "Assumed", note: "Scaled to each item's typical demand; see configs/base.yaml." },
  { item: "Prices, costs, penalties", kind: "Assumed", note: "Four category profiles. Not company figures." },
  { item: "Disruptions and data faults", kind: "Simulated", note: "Drawn per item and realization with fixed seeds; identical for every policy." },
];

export function DataPage() {
  const dq = useData<Loose>("data_quality");
  const fc = useData<Loose>("forecast");
  const evidence = useData<Loose>("research_evidence");
  if (dq.status === "loading") return <Loading label="Loading data checks" />;
  if (dq.status === "error") return <ErrorState message={dq.error} />;
  const d = dq.data;
  const synthetic = d.data_source === "synthetic_fixture";
  const daily = (d.daily as Loose[]).map((r) => ({ x: r.day_index, y: r.stockout_share, label: String(r.dt).slice(5) }));
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data and reliability</h1>
          <p>Where every number comes from, which checks the data passed, and what is assumed rather than observed.</p>
        </div>
      </div>

      {evidence.status === "ready" && <Panel title="FreshRetailNet-50K pilot" hint="Observed data from Dingdong-Inc, CC BY 4.0">
        <dl className="kv">
          <dt>Official training split</dt><dd className="num">{evidence.data.retail_source.dates.train.join(" to ")}</dd>
          <dt>Official evaluation split</dt><dd className="num">{evidence.data.retail_source.dates.eval.join(" to ")}</dd>
          <dt>Pilot data checks</dt><dd>{evidence.data.retail_source.rows_clean.toLocaleString("en-US")} rows passed, {evidence.data.retail_source.rows_quarantined} quarantined</dd>
          <dt>Publisher revision</dt><dd className="mono">{evidence.data.retail_source.provenance.revision.slice(0, 12)}</dd>
        </dl>
        <p className="small muted">Sales and stockout flags are observed. Demand during stockouts is estimated. Inventory, supplier conditions and costs are modeled.</p>
        <Link to="/benchmark?study=retail">Explore pilot results</Link>
      </Panel>}
      <div className="grid-2 section">
        <Panel title={synthetic ? "Synthetic fixture provenance" : "Provenance"}>
          <dl className="kv">
            <dt>Source</dt><dd>{synthetic ? "Synthetic fixture with the FreshRetailNet-50K schema" : "FreshRetailNet-50K (Dingdong-Inc, CC BY 4.0)"}</dd>
            <dt>Store-products</dt><dd className="num">{d.n_series}</dd>
            <dt>Days</dt><dd className="num">{d.n_days} ({d.date_range[0]} to {d.date_range[1]})</dd>
            <dt>Rows read</dt><dd className="num">{d.rows_raw.toLocaleString("en-US")}</dd>
            <dt>Rows quarantined</dt><dd className="num">{d.rows_quarantined} ({Object.entries(d.quarantine_reasons as Record<string, number>).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ") || "none"})</dd>
            <dt>Stock-out hour window</dt><dd className="num">{d.stock_count_hours[0]}:00 to {d.stock_count_hours[1] + 1}:00</dd>
            <dt>Ingested</dt><dd className="num">{String(d.ingested_at).replace("T", " ").replace("+00:00", " UTC")}</dd>
          </dl>
          {synthetic ? (
            <p className="callout warn" style={{ marginTop: 14 }}>
              The synthetic decision cases use the publisher's 19-column schema, generated stockouts and known latent demand. The controlled fixture supports direct tests of leakage and demand recovery.
            </p>
          ) : (
            <p className="small muted" style={{ marginTop: 14 }}>Attribution: FreshRetailNet-50K by Dingdong-Inc, CC BY 4.0. Wang et al., arXiv:2505.16319.</p>
          )}
        </Panel>
        <Panel title="Share of store-products with a stock-out, by day">
          <DailySeries points={daily} split={91} yFormat={(v) => pct(v, 0)} ariaLabel="Daily share of store-products with any out-of-stock hour" />
          <p className="xs faint">Days 91 to 97 mirror the official evaluation partition for the synthetic fixture.</p>
        </Panel>
      </div>

      <Panel title="Quality checks" pad={false}>
        <div className="table-wrap" style={{ padding: "4px 8px 8px" }}>
          <table className="data stack-sm">
            <thead><tr><th scope="col">Check</th><th scope="col">Severity</th><th scope="col">Result</th><th scope="col" className="r">Rows affected</th><th scope="col">Detail</th></tr></thead>
            <tbody>
              {(d.checks as Loose[]).map((c) => (
                <tr key={c.name}>
                  <td className="full" style={{ fontWeight: 500 }}>{titleCase(c.name.replace(/_/g, " "))}</td>
                  <td className="small" data-label="Severity">{c.severity === "hard" ? "Quarantine" : "Report"}</td>
                  <td data-label="Result"><span className={`chip ${c.passed ? "o-recommend" : c.severity === "hard" ? "o-reject" : "o-investigate"}`}>{c.passed ? "Passed" : c.severity === "hard" ? "Rows quarantined" : "Attention"}</span></td>
                  <td className="r num" data-label="Rows affected">{c.n_failed}</td>
                  <td className="small muted full">{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="section">
        <h2>Assumption register</h2>
        <p className="lede">Each input is labeled by how it was obtained. Results never present simulated or assumed values as company records.</p>
        <div className="panel table-wrap" style={{ padding: "4px 8px 8px" }}>
          <table className="data stack-sm">
            <thead><tr><th scope="col">Input</th><th scope="col">Kind</th><th scope="col">Note</th></tr></thead>
            <tbody>{REGISTER.map((r) => <tr key={r.item}><td style={{ fontWeight: 500 }}>{r.item}</td><td><span className="tag">{r.kind}</span></td><td className="small muted full">{r.note}</td></tr>)}</tbody>
          </table>
        </div>
      </div>

      {fc.status === "ready" && <ForecastQuality f={fc.data} />}
    </>
  );
}

const MODEL_LABEL: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  lgbm_point: "LightGBM point",
  lgbm_quantile_observed: "LightGBM quantiles, observed sales",
  lgbm_quantile_recovered: "LightGBM quantiles, stockout-aware",
  lgbm_quantile_recovered_nopromo: "Stockout-aware, no promotion inputs",
};

function ForecastQuality({ f }: { f: Loose }) {
  const hasLatent = Object.values(f.models as Record<string, Loose>).some((m) => m.vs_latent_all);
  const ce = f.censoring_experiment;
  return (
    <div className="section">
      <h2>Forecast evaluation</h2>
      <p className="lede">
        Final-stage models, evaluated on days {f.stage.forecast_targets[0]} to {f.stage.forecast_targets[1]}. Accuracy against observed sales is biased on stock-out days, so in-stock days
        {hasLatent ? " and, for the synthetic fixture, true demand" : ""} are shown separately.
      </p>
      <div className="panel table-wrap" style={{ padding: "4px 8px 8px" }}>
        <table className="data stack-sm stack-md">
          <thead>
            <tr>
              <th scope="col">Model</th><th scope="col" className="r">WAPE, in-stock days</th><th scope="col" className="r">Bias, in-stock days</th>
              <th scope="col" className="r">Pinball, all days</th><th scope="col" className="r">80% interval coverage</th>
              {hasLatent && <><th scope="col" className="r">Pinball vs true demand</th><th scope="col" className="r">Bias vs true demand</th></>}
            </tr>
          </thead>
          <tbody>
            {Object.entries(f.models as Record<string, Loose>).map(([k, m]) => (
              <tr key={k}>
                <td className="full" style={{ fontWeight: 500 }}>{MODEL_LABEL[k] ?? k}</td>
                <td className="r num" data-label="WAPE, in-stock">{pct(m.vs_observed_instock.wape)}</td>
                <td className="r num" data-label="Bias, in-stock">{pct(m.vs_observed_instock.bias, 1, true)}</td>
                <td className="r num" data-label="Pinball, all days">{units(m.vs_observed_all.pinball, 3)}</td>
                <td className="r num" data-label="80% coverage">{pct(m.vs_observed_all.coverage80, 0)}</td>
                {hasLatent && <><td className="r num" data-label="Pinball vs truth">{units(m.vs_latent_all?.pinball, 3)}</td><td className="r num" data-label="Bias vs truth">{pct(m.vs_latent_all?.bias, 1, true)}</td></>}
              </tr>
            ))}
          </tbody>
          <caption>WAPE: total absolute error over total sales. Pinball: mean quantile loss over seven levels. Coverage: share of outcomes inside the 10th to 90th percentile band.</caption>
        </table>
      </div>
      <div className="grid-2e" style={{ marginTop: 20 }}>
        <Panel title="Recovering demand hidden by stock-outs">
          <p className="small">{ce.design}. {ce.observed_as_demand.n} days.</p>
          <table className="data" style={{ marginTop: 8 }}>
            <thead><tr><th scope="col">Estimate</th><th scope="col" className="r">Mean abs. error</th><th scope="col" className="r">Bias</th></tr></thead>
            <tbody>
              <tr><td>Treat observed sales as demand</td><td className="r num">{units(ce.observed_as_demand.mae, 2)}</td><td className="r num">{ce.observed_as_demand.bias_pct.toFixed(1)}%</td></tr>
              <tr><td>Hourly-profile recovery</td><td className="r num">{units(ce.profile_recovery.mae, 2)}</td><td className="r num">{ce.profile_recovery.bias_pct.toFixed(1)}%</td></tr>
            </tbody>
          </table>
        </Panel>
        {ce.synthetic_genuine_stockouts && (
          <Panel title="Genuine stock-outs (synthetic truth only)">
            <p className="small">On {ce.synthetic_genuine_stockouts.n} real stock-out days in the fixture, observed sales understate true demand by {Math.abs(ce.synthetic_genuine_stockouts.observed_bias_pct).toFixed(1)}%; recovery leaves a bias of {ce.synthetic_genuine_stockouts.recovered_bias_pct.toFixed(1)}%. Real data cannot be checked this way.</p>
          </Panel>
        )}
      </div>
    </div>
  );
}
