# MASTER PROJECT DIRECTIVE — ENTERPRISE DECISION INTELLIGENCE

## 1. Your role and execution mandate

Act as an independent principal AI engineer, senior data scientist, data engineer, operations research scientist, enterprise solutions architect, UX designer, product manager, security engineer and QA lead.

Your responsibility is to research, design, implement, evaluate, test, document and deploy a complete, research-backed portfolio project named **Enterprise Decision Intelligence**.

Do not treat this as a tutorial, hackathon prototype, generic AI dashboard or proof of concept with superficial functionality. Build a polished, technically credible, enterprise-oriented reference implementation with working business workflows and reproducible experimental evidence.

Operate autonomously throughout the project. Make sensible engineering decisions without requesting approval for every minor detail. Challenge the assumptions in this directive wherever a better alternative exists. Record material deviations, supporting evidence, trade-offs and reasons before implementing them.

Never blindly assume that your initial implementation is correct. Perform multiple independent review passes covering business value, statistical methodology, architecture, software correctness, security, user experience and deployment.

Do not stop after creating a plan or scaffolding the repository. Execute the entire project through its completion gates wherever the environment permits.

Do not claim completion for work that has not been implemented, executed and verified.

---

## 2. Project identity

- Project name: Enterprise Decision Intelligence
- Repository: Enterprise-Decision-Intelligence
- Subtitle: Risk-aware business decision optimization and validation
- Author: Abhinav Varma Vathadi
- GitHub: https://github.com/AbhinavVarma02
- Development and infrastructure budget: $0 in incremental monetary expenditure
- Deployment platform: Cloudflare Pages
- Intended audience: Enterprise decision-makers, technical hiring managers, AI engineers, data scientists, data engineers, applied scientists and researchers.

Use straightforward, professional human language throughout the application and documentation.

Avoid excessive AI branding, exaggerated marketing terminology, unnecessary em dashes, generic AI-generated copy and unsupported claims of enterprise adoption.

The project should communicate credibility through its functionality, design, evidence and engineering quality.

---

## 3. Business problem and product vision

Large enterprises make consequential business decisions involving incomplete information, uncertain forecasts, changing demand, supplier disruptions, limited budgets and conflicting departmental objectives.

Existing forecasting and planning systems can generate recommendations, but an accurate prediction does not necessarily produce a financially sound decision. Organizations must also understand whether a proposed action remains feasible under uncertainty, what could happen if its assumptions are wrong, what delaying the decision would cost and whether obtaining additional information would improve the outcome.

Build an independent decision intelligence and validation framework that can evaluate recommendations from different forecasting models, optimization systems, enterprise planning systems and AI agents.

The platform must answer:

- What business problem requires attention?
- What is the financial and operational exposure?
- What happens if the organization takes no action?
- What alternative actions are available?
- Which actions remain feasible under business constraints?
- Which action produces the best risk-adjusted outcome?
- How sensitive is the recommendation to incorrect assumptions?
- Which missing information should be verified before committing?
- When should the system recommend, defer, reject or escalate a decision?
- How can the decision and its subsequent outcome be independently audited?

The goal is not to replace SAP, Oracle, Kinaxis or other enterprise platforms. Position this project as a vendor-independent reference implementation for evaluating and improving the reliability of business decisions.

The primary business implementation will focus on supply chain, inventory replenishment, procurement and disruption management.

The underlying framework must be designed for adaptation to other sectors, including manufacturing, semiconductors, retail, healthcare, finance, insurance, logistics, energy, telecommunications, technology and higher education.

Do not claim validated applicability to a sector unless a corresponding experiment or implementation supports it.

---

## 4. Mandatory initial research and independent plan review

Before writing production code, conduct a focused, evidence-based research phase.

### Enterprise research

Examine recent, credible sources concerning operational challenges faced by major enterprises, especially:

- Micron Technology
- Applied Materials
- Intel
- AMD
- Walmart
- Amazon
- Target
- Tyson Foods
- PepsiCo
- Other relevant Fortune 500 organizations

Prioritize annual reports, SEC filings, investor disclosures, official company publications and reputable industry research.

Investigate problems involving demand uncertainty, inventory imbalance, stockouts, supplier dependency, capacity constraints, procurement costs, working capital, operational disruptions and decision governance.

Do not assert that these companies lack internal solutions. Document their publicly disclosed business problems and explain how this project's methodology addresses related challenges.

### Competitive research

Investigate existing capabilities from:

- SAP Integrated Business Planning
- Kinaxis Maestro
- Aera Technology
- Oracle Supply Chain Management
- Stockpyl
- Relevant open-source decision intelligence, inventory optimization and forecasting repositories.

Starting references:

- https://www.sap.com/products/scm/integrated-business-planning-scenario-planning.html
- https://www.kinaxis.com/en/solutions/platform
- https://www.kinaxis.com/en/maestro-solver-studio
- https://www.aeratechnology.com/technology/decision-governance/
- https://stockpyl.readthedocs.io/en/latest/
- https://github.com/LarrySnyder/stockpyl

Identify existing functionality, overlapping capabilities, credible differentiation opportunities and limitations of this implementation relative to commercial platforms.

Never claim that a feature is novel simply because it is unfamiliar.

### Scientific research

Review relevant literature covering:

- Probabilistic forecasting
- Censored and latent demand estimation
- Forecast calibration
- Predict-then-optimize and decision-focused learning
- Stochastic programming
- Robust optimization
- Conditional Value at Risk (CVaR)
- Expected value of information
- Inventory simulation
- Decision regret
- Model uncertainty
- Human-in-the-loop decision-making
- Decision abstention
- Financial decision evaluation

Useful starting references:

- Smart Predict, then Optimize: https://arxiv.org/abs/1710.08005
- FreshRetailNet-50K paper: https://arxiv.org/abs/2505.16319
- Dataset: https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K
- Dataset baseline: https://github.com/Dingdong-Inc/frn-50k-baseline
- Related forecasting and optimization research: https://www.mdpi.com/2411-5134/11/5/89
- Stockpyl simulation documentation: https://stockpyl.readthedocs.io/en/latest/tutorial/tutorial_sim.html

Verify every material reference, publication date, license and factual claim before citing it.

Maintain `docs/RESEARCH.md` with source URLs, findings, relevance, publication or access dates, and limitations.

Maintain `docs/COMPETITIVE_ANALYSIS.md` with a feature comparison and a defensible statement of the project's differentiation.

### Independent review requirement

Review the proposed architecture and methodology before implementation from five perspectives:

1. Enterprise business stakeholder.
2. Data scientist and operations researcher.
3. Data engineer and production architect.
4. Security, governance and reliability reviewer.
5. Technical hiring manager and product designer.

Identify weaknesses, unnecessary complexity, feasibility risks, data limitations, better alternatives and potentially misleading claims.

Record the revised decisions in `docs/ARCHITECTURE.md` and architecture decision records.

Do not spend the entire execution budget on research. Complete a focused review and proceed to implementation.

---

## 5. Primary distinguishing contribution

The project's signature contribution must be an **open-source Decision Reliability Benchmark** supported by an independent decision validation engine.

The benchmark must evaluate business decisions, not merely the predictions that produced them.

Compare conventional and uncertainty-aware decision strategies under normal operating conditions, unreliable data and disruptive scenarios.

The contribution should combine:

- Financial and operational evaluation.
- Independent constraint validation.
- Decision stress testing.
- Cost of inaction.
- Tail-risk assessment.
- Value of additional information.
- Appropriate escalation and abstention.
- Reproducible decision replay.
- Transparent comparison across decision policies.

The central research hypothesis is:

Improving predictive accuracy does not necessarily improve downstream business outcomes, particularly when uncertainty, asymmetric financial costs, unreliable inputs and operational constraints affect the decision.

Treat this as a hypothesis to investigate, not a predetermined conclusion.

If experiments fail to support the hypothesis, report the actual findings and explain the circumstances.

---

## 6. Persistent project memory and cross-agent continuity

This requirement is mandatory.

Before substantive implementation begins, create the following files in the repository root.

### MASTER_PROMPT.md

Persist this complete master directive, preserving its requirements and structure as faithfully as possible.

Treat it as the canonical project specification.

Do not silently rewrite original requirements. Document approved or justified changes separately.

### AGENTS.md

Create concise, actionable instructions for Codex and other coding agents.

Include:

- Project purpose.
- Repository structure.
- Mandatory reading order.
- Development and testing commands.
- Architectural constraints.
- Budget restrictions.
- Research integrity requirements.
- Security rules.
- UI quality expectations.
- Completion criteria.
- Instructions for maintaining progress files.

### CLAUDE.md

Create equivalent Claude Code instructions referencing the canonical specification and shared repository documentation.

Avoid maintaining two conflicting copies of the project plan.

### PROGRESS.md

Maintain a continuously updated project status document containing:

- Last updated date and time.
- Current development phase.
- Completed tasks with verification evidence.
- Tasks in progress.
- Remaining tasks.
- Latest test results.
- Dataset status.
- Experiment results and artifact locations.
- Current implementation decisions.
- Known bugs and limitations.
- Deployment status.
- Latest verified commit.
- Immediate next actions.

Update it after each meaningful development milestone, before context compaction when practical, and before ending a session.

### HANDOFF.md

Maintain a compact handoff for the next coding agent containing:

- Current project state.
- Exact point where development stopped.
- Relevant changed files.
- Commands already executed.
- Known blockers.
- Uncommitted work.
- Outstanding tests.
- Immediate next executable task.

### TASKS.md

Maintain a prioritized implementation backlog with dependencies, acceptance criteria and status.

### CHANGELOG.md

Track meaningful changes, releases and verified improvements.

### docs/decisions/

Maintain architecture decision records for significant choices.

Each record should explain:

- Context.
- Alternatives considered.
- Selected approach.
- Reasons.
- Trade-offs.
- Consequences and validation.

### Recovery protocol

At the beginning of every future session, the coding agent must:

1. Read `AGENTS.md` or `CLAUDE.md`.
2. Read `MASTER_PROMPT.md`.
3. Read `PROGRESS.md`.
4. Read `HANDOFF.md` and `TASKS.md`.
5. Inspect Git status and recent commits.
6. Verify the current implementation rather than assuming the documents are perfectly accurate.
7. Resume the highest-priority incomplete task.

Never reinitialize or unnecessarily rebuild completed components.

Do not discard existing user changes.

Ensure the project can transition between Claude Code and Codex without relying on previous conversation history.

---

## 7. Dataset strategy and research integrity

### Primary real-world dataset

Use FreshRetailNet-50K:

https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K

Investigate its official data schema, train and evaluation partitions, stock-status indicators, temporal coverage, sales observations, external covariates and licensing.

Preserve attribution and comply with CC BY 4.0 requirements after verifying the applicable dataset revision.

Pin the dataset revision where possible and record checksums, retrieval instructions and provenance.

The dataset's principal advantage is that stockout annotations allow examination of censored demand.

Observed sales must not automatically be treated as true customer demand when products were unavailable.

### Data limitations

Clearly distinguish among:

- Real observed sales.
- Real stockout indicators.
- Estimated latent demand.
- Artificially censored demand experiments.
- Simulated inventory levels.
- Simulated supplier disruptions.
- Assumed procurement costs.
- Assumed financial parameters.

Never portray simulated supplier events, costs or savings as actual company records.

Because latent demand during genuine stockouts may be unobservable, use artificially censored periods with known demand for controlled recovery experiments where appropriate.

For real stockout periods, report estimates and sensitivity bounds rather than fabricated ground truth.

### Temporal integrity

Prevent temporal leakage.

- Use chronological training, validation and final test partitions consistent with the official dataset.
- Fit all preprocessing and calibration using permissible historical data.
- Avoid future-derived features.
- Verify whether weather, discounts and promotions would actually have been known at decision time.
- Use historical or forecast substitutes when necessary.
- Do not tune hyperparameters against the final test set.

### Resource constraints

Begin with a deterministic, documented subset sized appropriately for the local machine.

Expand experiments only when memory, compute, disk and runtime permit.

Provide separate development and full research configurations.

Do not commit large raw datasets or model binaries unnecessarily.

### Additional datasets

Evaluate M5 Forecasting or another appropriate public dataset only if it meaningfully strengthens external validation and licensing permits the intended use.

Do not add datasets merely to increase apparent scale.

If the primary dataset is temporarily unavailable, use a clearly labeled deterministic synthetic fixture to continue engineering and testing. Mark real-data experiments incomplete until they are actually executed.

---

## 8. Enterprise data engineering foundation

Build a credible data pipeline, not a notebook-only solution.

Recommended starting stack:

- Python
- DuckDB
- Parquet
- SQL
- dbt-core with DuckDB adapter, if justified
- Pandas or Polars, selected based on measured needs
- Lightweight reproducible orchestration
- GitHub Actions
- Pydantic or equivalent schema validation

Use a layered architecture:

- Raw ingestion.
- Validated and standardized data.
- Curated analytical tables.
- Forecast and feature tables.
- Decision snapshots.
- Benchmark results.
- Deployment artifacts.

Implement:

- Deterministic ingestion.
- Incremental processing where meaningful.
- Idempotent pipeline execution.
- Primary-key and uniqueness validation.
- Schema and null checks.
- Data freshness checks.
- Data lineage and provenance.
- Invalid-record quarantine.
- Structured logging.
- Failure recovery.
- Artifact versioning.
- Reproducible transformations.
- Clear separation between event time and ingestion time where applicable.

Do not add Kafka, Spark, Airflow or distributed infrastructure unless a specific requirement justifies them.

A working, tested lightweight pipeline is more credible than a collection of unnecessary infrastructure components.

---

## 9. Predictive intelligence

Implement a statistically defensible forecasting component.

Start with:

1. Seasonal naive forecast.
2. A suitable statistical or moving-average baseline.
3. A conventional machine learning model.
4. A probabilistic, stockout-aware forecasting approach.

Consider LightGBM quantile regression or another efficient CPU-compatible model.

Compare different approaches for handling censored demand, including naive observed-sales training and appropriately documented stockout-aware alternatives.

Produce predictive quantiles or distributions rather than only point predictions.

Evaluate:

- MAE.
- WAPE, with appropriate treatment of zero denominators.
- Forecast bias.
- Quantile pinball loss.
- Prediction interval coverage.
- Prediction interval width.
- Calibration.
- Performance across relevant product and stockout segments.

Use chronological backtesting and validation.

Ensure quantile predictions are coherent, nonnegative where required and properly calibrated.

Do not implement deep learning simply because it appears advanced.

If a simple model performs better or is more computationally efficient, prefer it and explain why.

---

## 10. Business simulation and disruption intelligence

Build a deterministic, seed-controlled operational simulation.

The primary simulation must represent inventory and procurement decisions involving:

- Products and locations.
- Available inventory.
- Replenishment lead times.
- Outstanding orders.
- Supplier capacity.
- Procurement budgets.
- Minimum order quantities.
- Holding costs.
- Shortage costs.
- Transportation and expediting costs.
- Perishable inventory or waste costs where applicable.
- Service-level requirements.
- Supplier eligibility.
- Decision deadlines.

Define the timing and ordering of simulation events explicitly.

Validate inventory conservation and financial accounting.

Implement representative disruption scenarios:

- Unexpected demand increase.
- Demand collapse.
- Supplier failure.
- Lead-time increase.
- Supplier capacity reduction.
- Procurement cost increase.
- Transportation disruption.
- Inventory-record inaccuracies.
- Stale data.
- Forecast distribution shift.
- Budget reductions.
- Combined disruptions.

Include a bounded supplier-product dependency graph to demonstrate how upstream disruptions can affect downstream products or operations.

Clearly distinguish scenario assumptions from observed empirical data.

Use common random numbers or equivalent matched scenario generation for fair policy comparisons.

Do not allow simulated decision policies to access future outcomes.

---

## 11. Financial decision intelligence

Build a transparent financial model that converts operational consequences into business-relevant metrics.

Include where appropriate:

- Procurement cost.
- Inventory holding cost.
- Shortage penalties or lost contribution margin.
- Expediting cost.
- Waste and obsolescence.
- Transportation cost.
- Working capital committed.
- Service-level penalties.
- Expected total operating cost.
- Financial downside under adverse scenarios.
- Cost of inaction.
- Incremental benefit relative to baseline.

Maintain consistent units, currency and time horizons.

Do not double-count lost sales, lost margin and shortage penalties.

Distinguish revenue, contribution margin, profit, cash expenditure and working capital.

Avoid inventing ROI, revenue improvements or company savings.

### Cost of inaction

Evaluate the expected consequences of delaying or declining intervention.

Compare:

- Act now.
- Wait for additional information.
- Take a smaller reversible action.
- Escalate.
- Take no action.

Model the effect of decision delay on inventory, feasible alternatives, lead times and potential financial losses.

### Financial uncertainty

Expose expected outcomes alongside downside risk.

Use appropriate measures such as:

- Expected cost.
- Cost quantiles.
- CVaR at a justified confidence level.
- Probability of exceeding a business-defined loss tolerance.
- Sensitivity to financial assumptions.

Allow business stakeholders to configure risk tolerance within validated bounds.

---

## 12. Mathematical decision optimization

Implement a rigorous optimization component.

Use SciPy HiGHS, OR-Tools or another appropriate free solver after examining the mathematical requirements.

Do not force a specific library if a simpler, verified formulation is more suitable.

The optimization problem should minimize expected or risk-adjusted business costs while satisfying operational constraints.

Support relevant decisions including:

- Order quantities.
- Supplier allocation.
- Replenishment timing.
- Expedited procurement.
- Alternative sourcing.
- Inventory redistribution where supported.
- Deferral or no-action decisions.

Implement conventional and risk-aware optimization strategies.

Document:

- Decision variables.
- Objective function.
- Hard constraints.
- Soft constraints.
- Units.
- Scenario assumptions.
- Solver settings.
- Optimality and feasibility status.

Handle infeasible problems explicitly.

Never silently relax hard business constraints or present an infeasible recommendation as valid.

Verify solutions independently from the solver.

Use brute-force enumeration on small test problems to validate mathematical correctness where feasible.

---

## 13. Independent decision reliability engine

Design the validation engine independently from the model that generated the recommendation.

It must accept standardized decision candidates and evaluate them against data quality, financial, operational and governance requirements.

Use a versioned decision schema containing:

- Decision identifier.
- Domain.
- Decision timestamp.
- Available data snapshot.
- Candidate action.
- Alternatives.
- Objective.
- Constraints.
- Forecast distribution.
- Financial assumptions.
- Scenario results.
- Model and policy versions.
- Risk tolerance.
- Validation evidence.
- Decision status.
- Approval requirements.

Implement explicit validation gates covering:

1. Data integrity and freshness.
2. Constraint satisfaction.
3. Financial consistency.
4. Uncertainty and downside risk.
5. Stress-case resilience.
6. Missing critical evidence.
7. Governance and approval requirements.

Possible outcomes:

- Recommend.
- Investigate.
- Defer.
- Escalate.
- Reject.

Do not conceal hard failures behind a weighted reliability score.

If a numerical reliability score is included, document how it is constructed and make clear that it cannot override hard safety or business constraints.

### Value of information

Implement a bounded, mathematically justified method for estimating whether obtaining additional information could improve the decision.

Compare the expected benefit of information against its acquisition cost and the cost of delaying action.

For controlled synthetic experiments, use observable latent states to establish theoretical reference values where appropriate.

Do not give a real decision policy access to hidden future information.

Clearly distinguish exact value-of-information calculations from approximations and perfect-information upper bounds.

### Exception prioritization

Prioritize business issues according to:

- Financial exposure.
- Urgency.
- Downside risk.
- Intervention feasibility.
- Expected benefit of action.
- Investigation cost.

Avoid flooding users with undifferentiated alerts.

---

## 14. Decision Reliability Benchmark

This is the project's most important research deliverable.

Create a standalone, reproducible benchmark capable of comparing different decision policies through a documented interface.

Compare at least the following meaningful approaches:

1. Conventional reorder or rule-based policy.
2. Point forecast plus deterministic optimization.
3. Probabilistic forecast plus expected-cost optimization.
4. Risk-aware stochastic or robust optimization.
5. Proposed decision validation and escalation framework.

Use a strong conventional policy rather than intentionally weak baselines.

The proposed framework may wrap existing policies; compare like-for-like underlying policies to isolate the benefit of the validation layer.

Include ablation studies where feasible:

- Without stockout-aware forecasting.
- Without risk-aware optimization.
- Without independent validation.
- Without value-of-information analysis.
- Without escalation.

### Benchmark metrics

Evaluate:

- Total simulated business cost.
- Expected cost.
- Tail loss and CVaR.
- Decision regret relative to clearly defined reference policies.
- Constraint violations.
- Service level.
- Stockout frequency.
- Inventory waste.
- Working capital.
- Unsafe recommendation detection.
- Unnecessary escalation rate.
- Decision coverage.
- Investigation and escalation costs.
- Runtime.
- Reproducibility.

If a perfect-information oracle is used, report it explicitly as a retrospective upper bound, not a deployable policy.

Define unsafe decisions objectively before evaluation.

Evaluate selective decision-making through the trade-off between recommendation coverage and unsafe-decision rates.

Do not allow the framework to appear superior merely by escalating every difficult decision. Include the cost and consequence of escalation.

### Experimental integrity

- Predefine core hypotheses and evaluation metrics.
- Freeze the final evaluation protocol before inspecting final results.
- Use matched scenarios and deterministic seeds.
- Separate tuning scenarios from held-out disruption scenarios.
- Include multiple independent scenario realizations.
- Report uncertainty intervals using an appropriate resampling or statistical method.
- Report negative findings.
- Conduct sensitivity analysis on cost assumptions and risk tolerances.
- Preserve experiment configurations and raw result artifacts.

Publish a machine-readable benchmark summary and human-readable technical analysis.

Do not fabricate statistical significance, numerical improvements or successful experiments.

---

## 15. Cross-industry generalization

Do not implement numerous shallow industry dashboards.

Build one complete primary domain and one smaller but meaningful secondary domain.

### Primary domain

Inventory, procurement and supply chain disruption decisions using real retail observations combined with transparently simulated operational inputs.

### Secondary domain

Prefer a cloud infrastructure capacity and cost-allocation scenario, or another defensible non-inventory resource allocation problem.

The secondary domain should involve materially different business constraints, such as capacity reservations, on-demand costs, service requirements and time-sensitive workloads.

Use appropriately licensed real data if available at zero cost; otherwise, use an explicitly synthetic, reproducible scenario.

Demonstrate reuse of:

- Decision candidate schema.
- Financial evaluation interface.
- Risk assessment.
- Validation gates.
- Scenario evaluation.
- Governance workflow.
- Benchmark and replay infrastructure.

Document what remains domain-specific.

Do not claim generalization simply by changing labels from products to hospital beds or employees.

---

## 16. AI and explanation architecture

The project does not require a commercial LLM or a continuously running AI model.

Machine learning, uncertainty modeling and mathematical optimization constitute the primary intelligence.

Implement an evidence-grounded explanation layer that translates verified numerical outputs into clear business language.

Prefer deterministic structured explanations as the default public experience.

Every explanation must be linked to actual computed evidence, constraints and scenario results.

For example:

"The expedited order has a lower expected cost, but the alternative sourcing strategy produces a lower modeled downside loss. Supplier eligibility must be confirmed before approval."

Do not allow an LLM to calculate financial metrics, override constraints, invent evidence or authorize transactions.

An optional local Ollama-based explanation adapter may be implemented only if it adds demonstrable value, runs within available hardware and does not introduce mandatory dependencies.

No paid APIs.

The complete application must remain functional without any LLM.

---

## 17. Premium UI and user experience — mandatory flagship quality

The interface is a critical project requirement, not a secondary task.

Review the visual quality, hierarchy, typography, navigation, interaction patterns and consistency of the author's previous projects.

References:

- Clinical-Trace AI: https://github.com/AbhinavVarma02/Clinical-Trace-AI
- Healthcare Payment Integrity: https://healthcare-payment-integrity.pages.dev/
- Patient Outreach Optimization: https://patient-outreach-optimization.pages.dev/
- GitHub portfolio: https://github.com/AbhinavVarma02

Inspect the actual available applications or screenshots where possible.

Use them as quality benchmarks only.

Do not copy their layouts, visual identities or component arrangements mechanically.

Create a unique, premium enterprise design identity for Enterprise Decision Intelligence.

You have independent creative freedom regarding the visual direction, typography, color palette, navigation architecture and information presentation.

### Design expectations

The application should feel like a credible decision workspace designed for enterprise executives, analysts and operational teams.

Prioritize:

- Exceptional typography and information hierarchy.
- Restrained and coherent color usage.
- Intentional spacing.
- High-quality data visualization.
- Precise financial formatting.
- Professional tables.
- Consistent interaction patterns.
- Subtle animation where useful.
- Clear focus states.
- Responsive layouts.
- Accessible contrast.
- Thoughtful empty, error and loading states.
- Consistent component styling.
- Fast perceived performance.
- Clear distinction between actual research results and illustrative scenarios.

Avoid:

- Generic AI dashboard templates.
- Excessive gradients.
- Unnecessary glassmorphism.
- Oversized hero sections.
- Decorative charts with no analytical value.
- Excessive badges.
- Random icon usage.
- Repetitive card grids.
- Artificial intelligence-themed neon graphics.
- Long explanatory text that overwhelms the business workflow.
- Buttons or filters that do not work.

Do not design the entire interface as a generic grid of KPI cards.

Create a distinctive workspace organized around reviewing, comparing, validating and approving business decisions.

Use concise copy written for real business users.

### Suggested application information architecture

You may refine the navigation if a better design emerges.

**Overview**

Executive-level summary showing financial exposure, prioritized exceptions, operational risks and decisions requiring review.

Clearly identify the highest-priority issue and allow the user to enter its decision workflow.

**Decision Workspace**

The signature application experience.

Show:

- Business problem and urgency.
- Relevant evidence.
- Forecast uncertainty.
- Current operational state.
- Candidate actions.
- Financial trade-offs.
- Recommended action.
- Risk assessment.
- Hard constraint status.
- Missing information.
- Approval or escalation requirements.

Make comparison between alternatives intuitive.

**Scenario Studio**

Allow users to modify bounded business assumptions such as demand changes, supplier delays, budget, procurement cost and risk tolerance.

Recalculate decision alternatives and associated outcomes.

Show how the recommended action changes when assumptions change.

**Benchmark and Research**

Present verified experimental findings, policy comparisons, uncertainty intervals, ablation studies and research conclusions.

Use charts that answer meaningful research questions rather than simply displaying every available metric.

**Data and Reliability**

Present provenance, data freshness, validation results, assumptions and critical data limitations.

**Decision History**

Allow users to review locally recorded decisions, compare previous snapshots and replay decision scenarios.

Clearly label simulated approvals and execution events.

**Methodology**

Provide a concise explanation of the system, architecture, data, financial model, evaluation methodology, limitations and source references.

### Signature experience

A user should be able to enter the application, understand the most important business problem, inspect alternative actions, modify a disruption assumption, observe the resulting financial consequences, review missing evidence and approve or escalate the simulated decision.

This workflow must be coherent, visually distinctive and functional from beginning to end.

### UI implementation

Prefer React, TypeScript and Vite.

Select appropriate free, maintained charting, icon and styling libraries.

Use a shared design system with documented tokens and reusable components.

Build keyboard-accessible interactions.

Avoid paid fonts, paid assets, premium component licenses and external services.

Use properly licensed locally hosted or system fonts.

### Mandatory visual QA

Do not evaluate the interface solely from source code.

Use Playwright or equivalent browser tooling to:

- Open every application page.
- Capture desktop, tablet and mobile screenshots.
- Inspect the rendered visual hierarchy.
- Identify overflow and clipping.
- Verify charts, tooltips and filters.
- Test navigation and interactive controls.
- Verify empty and error states.
- Check keyboard accessibility.
- Identify generic or inconsistent styling.

Perform an initial design review and at least one substantive editorial and visual refinement pass.

Save representative final screenshots and document the visual design system.

Do not declare the UI premium solely because the application renders successfully.

---

## 18. Zero-dollar architecture and Cloudflare deployment

The application must have no incremental paid infrastructure, hosting, API or model-inference dependencies.

Existing computer hardware, internet connectivity and already available coding-agent subscriptions are assumed; do not purchase additional services or credits.

Do not enable paid Cloudflare plans, Containers, paid databases, metered AI services or external API subscriptions.

### Preferred deployment architecture

Use two complementary execution environments.

**Local research and computation environment**

Python handles:

- Dataset ingestion.
- Data engineering.
- Model training.
- Extensive optimization.
- Simulation.
- Benchmark experiments.
- Validation.
- Artifact generation.

Provide a documented CLI or equivalent reproducible command interface.

**Public Cloudflare Pages application**

The frontend serves:

- Versioned research artifacts.
- Precomputed benchmark results.
- Representative business scenarios.
- Interactive decision analysis.
- Lightweight deterministic browser-side calculations.
- Locally stored demonstration decision records.

Use TypeScript and browser-side computation for bounded interactive scenario evaluation.

Use Web Workers if computational workloads would otherwise block the interface.

The browser demo may optimize over a documented, bounded candidate-action space rather than running the complete offline research solver.

Clearly identify this distinction.

Validate browser calculations against corresponding Python golden fixtures and equivalent algorithms wherever parity is claimed.

Do not silently substitute static results for live calculations.

If a requested scenario exceeds supported browser limits, provide a clear explanation and local-computation instructions.

No mandatory remote Python inference.

No continuously running backend.

A local FastAPI adapter may be added only if it meaningfully supports an actual integration requirement; it must not be necessary for the public application.

### Cloudflare constraints

Verify current official documentation before deployment:

- https://developers.cloudflare.com/pages/platform/limits/
- https://developers.cloudflare.com/pages/functions/pricing/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/

Keep assets comfortably below applicable platform limits.

Use compact JSON artifacts, lazy loading, compression where supported and appropriate caching.

Avoid requiring visitors to download complete research datasets.

Do not introduce Pages Functions or Workers unless there is a concrete, verified requirement that can remain within a hard zero-cost architecture.

### Deployment

Use the official Cloudflare Pages deployment workflow and the free `pages.dev` domain.

Preferred project slug: `enterprise-decision-intelligence`, subject to availability.

Inspect the available Cloudflare authentication and account configuration.

Deploy only to the intended account and a project dedicated to this application.

Do not overwrite or modify the author's previous projects.

Do not request payment information or upgrade a subscription.

If credentials or permissions are unavailable, finish and verify the production build locally and provide exact deployment commands.

Record the actual deployed URL only after successful verification.

Never invent a deployment URL or claim a successful deployment that did not occur.

---

## 19. Enterprise governance, security and integration

Implement a credible demonstration of decision governance.

Include:

- Configurable business policies.
- Approval thresholds.
- Supplier or action eligibility.
- Decision reasons.
- Audit event records.
- Model and artifact version tracking.
- Data snapshot identifiers.
- Simulated approval and rejection.
- Decision replay.
- Exportable decision records.

For the public demo, use browser-local storage or another free, appropriate client-side mechanism.

Do not claim browser-local records are tamper-proof, enterprise-compliant or centrally secured.

No real financial transactions, purchase orders or external system modifications.

Provide a documented JSON-based integration contract that could accept decisions from external enterprise systems.

A mock ERP adapter and validated import/export workflow are sufficient to demonstrate interoperability.

Do not claim live SAP or Oracle integration unless actually implemented and verified.

Security requirements:

- No secrets in source code.
- No credentials in frontend bundles.
- Validate imported data.
- Bound file sizes and computation workloads.
- Sanitize untrusted content.
- Avoid insecure dynamic execution.
- Review dependencies and licenses.
- Use appropriate security headers.
- Avoid unnecessary collection of personal information.
- Include a concise threat model.

The public application is an educational enterprise reference implementation, not a certified production decision system.

---

## 20. Repository organization

Use a clean, maintainable monorepo structure.

Suggested structure:

    Enterprise-Decision-Intelligence/
      MASTER_PROMPT.md
      AGENTS.md
      CLAUDE.md
      PROGRESS.md
      HANDOFF.md
      TASKS.md
      CHANGELOG.md
      README.md
      LICENSE
      THIRD_PARTY_NOTICES.md
      pyproject.toml
      .gitignore
      .github/
        workflows/
      apps/
        web/
      src/
        ingestion/
        data_quality/
        forecasting/
        simulation/
        finance/
        optimization/
        validation/
        information_value/
        benchmark/
        domains/
        integrations/
      configs/
      schemas/
      pipelines/
      scripts/
      experiments/
      tests/
      artifacts/
      docs/
        decisions/
        research/
        architecture/
        screenshots/
      data/
        README.md

Adapt the structure where necessary.

Avoid unnecessary abstractions and empty modules.

Keep raw datasets, caches, credentials, generated environments, temporary outputs and large model artifacts outside version control.

Commit lightweight reproducibility metadata and distributable artifacts where licensing and file size permit.

Pin dependencies using appropriate lockfiles.

Provide cross-platform setup instructions for Windows with WSL2 and Linux.

---

## 21. Testing and verification

Testing is mandatory across all major components.

### Scientific and data tests

Verify:

- Dataset integrity.
- Temporal ordering.
- Leakage prevention.
- Feature availability.
- Schema consistency.
- Forecast bounds.
- Quantile coherence.
- Calibration computations.
- Reproducible splits.
- Experiment reproducibility.

### Financial and simulation tests

Verify:

- Inventory conservation.
- Nonnegative quantities where required.
- Financial arithmetic.
- Unit consistency.
- Correct lead-time behavior.
- Procurement constraints.
- No double-counting.
- Cost-of-delay calculations.
- Risk aggregation.
- Correct handling of zero demand and extreme assumptions.

### Optimization tests

Verify:

- Known analytical solutions.
- Small exhaustive-search reference problems.
- Constraint satisfaction.
- Infeasibility detection.
- Deterministic behavior where required.
- No silent constraint relaxation.

### Decision reliability tests

Verify:

- Invalid-input detection.
- Critical stale-data handling.
- Hard-policy violations.
- Risk-threshold behavior.
- Appropriate escalation.
- Value-of-information calculations.
- No-action alternatives.
- Adversarial or inconsistent inputs.
- Complete audit evidence.

### Frontend tests

Verify:

- Calculation parity with golden fixtures.
- User inputs.
- Scenario recalculation.
- Navigation.
- Charts.
- Decision comparisons.
- Approval and escalation workflows.
- Persistence and reset behavior.
- Error handling.
- Accessibility.

### End-to-end tests

Use Playwright to test complete business decision journeys.

Include desktop and mobile viewport coverage.

### Release gate

Run linting, type checking, unit tests, integration tests, relevant property-based tests, frontend tests, browser tests, security checks and the production build.

Report actual test counts and results.

Do not artificially inflate test counts with redundant tests.

A failing material test blocks release until corrected or explicitly documented as a blocker.

---

## 22. Research and engineering documentation

Create a concise, professional public README with:

- Clear business problem.
- Solution overview.
- Live demonstration URL, once verified.
- Representative screenshots.
- Architecture diagram.
- Major capabilities.
- Signature research contribution.
- Verified benchmark findings.
- Technology stack.
- Reproduction instructions.
- Data attribution.
- Limitations.
- Repository organization.
- References.

Use accurate Mermaid architecture diagrams where appropriate.

Keep the README understandable to nontechnical hiring managers while providing sufficient technical links for engineers.

Maintain supporting documentation covering:

- Business requirements.
- Competitive analysis.
- Research sources.
- Architecture.
- Data model and lineage.
- Forecast methodology.
- Optimization formulation.
- Financial assumptions.
- Decision validation.
- Experiment protocol.
- Benchmark findings.
- Security and governance.
- Deployment and operations.
- Known limitations.

Create an extended master technical guide in a local-only documentation directory if requested or if practical within the execution budget.

The extended guide should explain why important methods were chosen, alternatives rejected, implementation trade-offs, research findings, debugging lessons and interview discussion points.

Do not automatically publish private or internal working notes containing sensitive information.

---

## 23. Career relevance

The project should demonstrate credible competencies for several target roles without artificially forcing every technology into the system.

**AI Engineer:** Evidence-grounded explanations, structured decision interfaces, governance, reliability and enterprise integration.

**Data Scientist:** Statistical modeling, time-series forecasting, uncertainty estimation, causal caution, hypothesis testing and decision evaluation.

**Machine Learning Engineer:** Reproducible pipelines, model versioning, inference contracts, monitoring and validation.

**Data Engineer:** SQL, data modeling, incremental processing, lineage, data-quality checks, reproducibility and failure recovery.

**Applied Scientist:** Mathematical optimization, experimental design, uncertainty analysis and rigorous comparisons.

**Data Analyst and BI Engineer:** Financial metrics, interactive analytics, interpretable business reporting and stakeholder-oriented communication.

**Forward Deployed Engineer:** Enterprise workflow integration, translating business requirements into reliable solutions, product delivery and stakeholder trade-offs.

Ensure these competencies are demonstrated through working artifacts, not merely mentioned in documentation.

---

## 24. Execution phases and acceptance gates

Execute the project in logical phases, maintaining progress and handoff files throughout.

### Phase 0 — Project initialization

Create persistent context files, inspect the local environment, establish the repository and verify available tools.

Acceptance gate: A new coding agent can understand the complete project from the repository alone.

### Phase 1 — Research and architecture

Complete business research, competitive review, scientific literature review, dataset assessment and architecture decisions.

Acceptance gate: A credible business problem, differentiated contribution, zero-cost architecture and reproducible experimental protocol are documented.

### Phase 2 — Data engineering

Implement ingestion, validation, transformation, provenance and analytical tables.

Acceptance gate: Deterministic data processing succeeds and integrity tests pass.

### Phase 3 — Forecasting

Train and compare appropriate baseline and probabilistic forecasting models.

Acceptance gate: Verified forecasting metrics, leakage checks and documented limitations.

### Phase 4 — Simulation and financial modeling

Implement operational scenarios, inventory transitions, supplier disruption modeling and financial evaluation.

Acceptance gate: Verified conservation, financial correctness and reproducible scenario execution.

### Phase 5 — Decision optimization

Implement conventional and risk-aware decision policies.

Acceptance gate: Correct optimization results on reference problems and explicit handling of infeasibility.

### Phase 6 — Decision reliability

Implement independent validation, stress testing, cost of inaction, value of information and escalation.

Acceptance gate: The engine correctly identifies known invalid decisions and handles uncertainty transparently.

### Phase 7 — Benchmark and research experiments

Run policy comparisons, held-out disruptions, ablations and sensitivity analysis.

Acceptance gate: Actual reproducible benchmark artifacts and honest research conclusions.

### Phase 8 — Secondary-domain validation

Implement a bounded, meaningful second-domain experiment.

Acceptance gate: Reuse of the core decision framework is demonstrated and domain-specific limitations are documented.

### Phase 9 — Premium application

Build the complete interactive application, design system, business workflows and visualizations.

Acceptance gate: All core user journeys work and rendered visual quality passes an independent review.

### Phase 10 — Final engineering and scientific review

Perform comprehensive testing, security checks, research-integrity review, editorial refinement and visual QA.

Acceptance gate: No unresolved critical correctness, security or usability issues.

### Phase 11 — Documentation and deployment

Finalize documentation, produce a verified production build and deploy to Cloudflare Pages if authenticated and authorized.

Acceptance gate: The public application works, the core workflows are verified and the documentation accurately describes the implementation.

### Execution prioritization

Do not let optional features prevent completion of the core project.

Prioritize in this order:

1. Correctness and business value.
2. Reproducible benchmark.
3. Financial and decision reliability methodology.
4. Premium functional user experience.
5. Documentation and deployment.
6. Optional extensions.

Deliver a polished, working vertical slice early, then expand its validated functionality.

If time, context, hardware or dataset availability limits execution, preserve working functionality and clearly record incomplete work.

---

## 25. Mandatory independent final review

Before declaring completion, conduct the following reviews.

**Business review:** Can a procurement manager, operations director or CFO understand the problem, available decisions, financial exposure and recommended next action?

**Scientific review:** Are the experiments fair, temporally valid, reproducible and supported by actual data?

**Financial review:** Are units consistent, costs correctly calculated and simulated outcomes honestly reported?

**Architecture review:** Is the system maintainable, appropriately scoped and free of unnecessary complexity?

**Reliability review:** Does the system detect invalid decisions, communicate uncertainty and escalate when justified?

**UI review:** Does the rendered experience meet the visual quality of the reference portfolio projects while establishing a unique design identity?

**Security review:** Are credentials protected and external effects appropriately constrained?

**Budget review:** Does the complete public application function without paid infrastructure or API dependencies?

**Hiring-manager review:** Does the project clearly communicate differentiated technical capabilities and meaningful enterprise business value?

Fix material weaknesses uncovered during these reviews.

Re-run affected tests after fixes.

Do not mistake an attractive application, successful build or large number of files for project completion.

---

## 26. Final delivery requirements

At the end of execution, provide a concise, evidence-based delivery report containing:

- Project status.
- Implemented business workflows.
- Architecture summary.
- Actual dataset used.
- Verified experimental findings.
- Benchmark comparison.
- Key limitations.
- Differentiation relative to existing solutions.
- Actual test results.
- Performance measurements.
- UI screenshots.
- Production build status.
- Verified Cloudflare deployment URL, if deployed.
- Git status and final commit identifier, if available.
- Reproduction commands.
- Development and hosting cost assessment.
- Remaining issues or blocked items.

Provide two strong, truthful resume bullet points derived exclusively from verified project results.

Do not invent percentages or business outcomes.

Create meaningful local Git commits throughout development where possible.

Do not publish to a remote GitHub repository without authorization to publish, and never overwrite an unrelated repository.

Update `PROGRESS.md`, `HANDOFF.md`, `TASKS.md` and `CHANGELOG.md` to reflect the actual final state.

---

## 27. Non-negotiable principles

- Zero incremental monetary expenditure.
- No paid infrastructure or commercial AI dependency.
- No fabricated metrics.
- No unsupported novelty claims.
- No misleading enterprise production claims.
- No leakage or manipulated benchmark comparisons.
- No hidden synthetic-data assumptions.
- No unnecessary technology stacking.
- No generic or unfinished user interface.
- No nonfunctional controls disguised as working features.
- No unverified deployment claims.
- No destructive changes to other projects.
- No reliance on conversation history for project continuity.
- No declaring success before verification.

Prefer a smaller, scientifically credible, beautiful and fully functional product over an oversized incomplete system.

The finished project should demonstrate the ability to identify a real enterprise business problem, research existing solutions, design a technically justified alternative, implement reliable software, evaluate measurable outcomes and deliver an exceptional user experience.

Begin execution now.

First persist this directive and initialize the project continuity files. Inspect the environment, research the problem, independently revise the implementation plan and then proceed autonomously through development, testing, refinement and deployment.

Do not stop after presenting a proposed plan. Build the project.
