# ADR-0007: How escalation, investigation and deferral act in the simulator

Status: accepted (2026-11-25)

Context. To measure the validation layer, its outcomes must change what happens in the simulation, with costs.

Decision.
- Recommend: execute the candidate.
- Reject: execute the validator's repaired action (the wrapped policy re-solved with authoritative constraints). Logged as a rejection.
- Investigate: pay the cycle-count cost, observe true on-hand, re-solve the wrapped policy with corrected inventory.
- Defer: place no order today; the next day's decision proceeds normally.
- Escalate: pay the review cost; the modeled reviewer re-solves with authoritative constraints, verified inventory and the risk-aware objective. With probability `reviewer_error_rate` the reviewer approves the original candidate unchanged.

Reasons. These are conservative, explicit assumptions that charge for every intervention and never give anyone future demand.

Trade-offs. Real reviewers vary; sensitivity runs vary review cost and reviewer error rate.
