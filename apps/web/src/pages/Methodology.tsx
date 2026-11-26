import { Link } from "react-router-dom";

const FLOW = [
  { t: "Sales and stock flags", s: "observed" },
  { t: "Demand recovery", s: "estimated where stock ran out" },
  { t: "Quantile forecast", s: "calibrated" },
  { t: "Policy proposes an order", s: "P1 to P4" },
  { t: "Independent validator", s: "seven gates", key: true },
  { t: "Outcome", s: "recommend, investigate, defer, escalate or reject" },
  { t: "Simulated execution", s: "true state and terms" },
  { t: "Benchmark metrics", s: "cost, risk, safety" },
];

function FlowDiagram() {
  return (
    <ol className="flow" aria-label="From data to forecast, policy, validation, simulated execution and benchmark metrics">
      {FLOW.map((f) => (
        <li key={f.t} className={f.key ? "key" : undefined}>
          <strong>{f.t}</strong>
          <span>{f.s}</span>
        </li>
      ))}
    </ol>
  );
}

export function Methodology() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Methodology</h1>
          <p>How decisions are generated, checked and scored, and what this project does not claim.</p>
        </div>
      </div>
      <div className="panel panel-pad" style={{ marginBottom: 24 }}><FlowDiagram /></div>
      <div className="prose">
        <h3>The question</h3>
        <p>A forecast can be accurate and still lead to a poor order when stock is perishable, shortages cost more than leftovers, suppliers fail or the data feeding the plan is wrong. This project scores decisions, not predictions, and asks when an independent check should approve, verify, wait, escalate or block a proposed order.</p>

        <h3>Data</h3>
        <p>FreshRetailNet-50K (Dingdong-Inc, CC BY 4.0) contains 50,000 store-product series across 90 training days and seven evaluation days. The retail pilot samples 60 series. Observed hourly stockout flags identify censored sales. Hourly sales profiles estimate demand where stock ran out. Supplier terms, prices, costs, disruptions and data faults are modeled. Decision workspace cases use a separate synthetic fixture with known latent demand.</p>

        <h3>Forecasting</h3>
        <p>We compare seasonal naive and weekday-adjusted moving averages with LightGBM point and quantile models. We calibrate prediction intervals on a separate week and enforce ordered quantiles. The retail pilot uses trailing weather and excludes published discount and activity values because their availability at decision time is unknown. Policy tuning ends before the official evaluation week.</p>

        <h3>Decisions and the simulator</h3>
        <p>Each day a policy chooses quantities from a primary supplier, an alternate supplier and expedited freight. HiGHS solves a mixed-integer program over 100 paths in the synthetic benchmark or 40 in the retail pilot. The risk-aware policy also minimizes Conditional Value at Risk. The simulator consumes the oldest inventory first and removes expired units. Shortage costs include lost revenue and a separate goodwill penalty.</p>

        <h3>Validation</h3>
        <p>The validator receives a standardized decision record and the authoritative terms of record, never the policy itself. It runs seven gates: data integrity and freshness, constraint satisfaction, financial consistency, downside risk, stress resilience, missing evidence and governance. Hard failures are never averaged away. When an input looks wrong, it prices a cycle count with the value of verification against the proposed order and with the expected value of perfect information. Every investigation and review is charged in the benchmark.</p>

        <h3>Benchmark protocol</h3>
        <p>Policies face identical worlds (common random numbers) under normal operations, unreliable data and disruptions that were not used for tuning. Parameters, including the validator's soft thresholds, are tuned on days 77 to 90 only. Unsafe decisions are defined before evaluation: a hard-constraint breach under true conditions, or expected regret under the true state above half a day of revenue. Uncertainty uses a cluster bootstrap over store-products. The protocol and its amendments are in <code>docs/EXPERIMENT_PROTOCOL.md</code>.</p>

        <h3>What runs where</h3>
        <ul>
          <li>Offline, in Python: ingestion, quality checks, forecasting, the mixed-integer policies, simulation and the benchmark.</li>
          <li>In this browser: the scenario evaluator, a bounded grid search (at most 390 order combinations, before budget filtering, over 300 demand scenarios) and the full validator, checked against Python on golden fixtures in the test suite.</li>
          <li>Nothing runs on a server. Records you create stay in this browser.</li>
        </ul>

        <h3>Limitations</h3>
        <ul>
          <li>Costs are assumptions on normalized volumes. No figure here is a company's real cost or saving.</li>
          <li>One echelon, one item at a time, a seven-day test window, simulated suppliers.</li>
          <li>Reviewers are modeled, not observed: a reviewer verifies stock and re-plans with a risk-aware objective, and errs at a fixed rate.</li>
          <li>Browser-local history is hash-chained but not tamper-proof and not a compliance record.</li>
          <li>The second domain (cloud capacity) is synthetic and smaller; it shows reuse of the contract and validator, not validated performance in that industry.</li>
        </ul>

        <h3>Reproduce</h3>
        <p>Install with <code>pip install -e ".[dev,download]"</code>. Use <code>configs/research.yaml</code> for a new synthetic run and <code>configs/research-real.yaml</code> for the pinned FreshRetailNet pilot. The downloader records source checksums. The pilot exports a separate evidence file.</p>

        <h3>References</h3>
        <ul>
          <li>Wang et al. FreshRetailNet-50K. arXiv:2505.16319 (2025).</li>
          <li>Elmachtoub and Grigas. Smart "Predict, then Optimize". arXiv:1710.08005.</li>
          <li>Rockafellar and Uryasev. Optimization of Conditional Value-at-Risk. Journal of Risk 2(1), 2000.</li>
          <li>Romano, Patterson and Candès. Conformalized Quantile Regression. NeurIPS 2019.</li>
          <li>DeHoratius and Raman. Inventory Record Inaccuracy: An Empirical Analysis. Management Science 54(4), 2008.</li>
          <li>Huh, Levi, Rusmevichientong and Orlin. Adaptive Data-Driven Inventory Control with Censored Demand. Operations Research 59(4), 2011.</li>
          <li>Nahmias. Perishable Inventory Theory: A Review. Operations Research 30(4), 1982.</li>
          <li>Geifman and El-Yaniv. Selective Classification for Deep Neural Networks. NeurIPS 2017.</li>
          <li>Azar. A Reproducible, Leakage-Free Pipeline for Censored Demand Forecasting and Inventory Optimization on FreshRetailNet-50K. Inventions 11(5):89, 2026.</li>
        </ul>
        <p className="small muted">Source code and full documentation: <a href="https://github.com/AbhinavVarma02" rel="noreferrer">github.com/AbhinavVarma02</a>. See also the <Link to="/benchmark">benchmark</Link>.</p>
      </div>
    </>
  );
}
