# ADR-0004: Stockpyl as comparator, not dependency

Status: accepted (2026-11-25)

Context. Stockpyl (MIT) provides inventory models and simulation. Our simulator needs fixed-life FIFO perishability, three suppliers with MOQ and budget, record errors and stale snapshots in one decision loop.

Decision. Implement a small purpose-built simulator; cite Stockpyl in the competitive analysis; cross-check the classic newsvendor critical-fractile solution analytically in tests rather than through Stockpyl.

Reasons. The required features are outside Stockpyl's documented single-node models; a dependency would not remove much code.

Trade-offs. Our simulator has less external validation. Mitigated by conservation and accounting property tests and analytical newsvendor checks.
