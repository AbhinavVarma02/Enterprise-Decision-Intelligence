# ADR-0009: Validator refinements found during engineering

Status: accepted (2026-11-25)

Context. Early runs exposed two design flaws in the validator and one in the governance rule.

1. **G3 compared a policy's in-sample SAA cost with an independent estimate.** In-sample optimization is biased low (the optimizer's curse) and both estimates carry Monte Carlo error, so 15 to 18% gaps appeared on sound decisions and triggered rejections.
   Decision: G3 now asks two separate questions. (a) Does the claimed cost reconcile with the candidate's own stated terms, within a standard-error allowance? (b) How much do the candidate's price and lead assumptions change cost compared with authoritative terms, measured on common scenarios (no sampling noise)?
2. **Textbook EVPI understated the value of a cycle count.** EVPI compares perfect information with the best hedged action under the prior. The validator's real alternative to verifying is to execute the candidate, which was planned on the suspect record.
   Decision: report EVPI and also the value of verification relative to the candidate, E_prior[C(candidate)] - V1, and investigate when the latter exceeds the cost. Both are exact over the discrete prior and bounded action grid.
3. **Expedite-share approvals at the end of a finite window.** See protocol amendment 1.

Consequences. Unit tests cover each behavior (`tests/test_validation.py`). These changes were made before any reported benchmark run.
