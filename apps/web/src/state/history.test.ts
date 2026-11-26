import { beforeEach, describe, expect, it } from "vitest";
import { append, resetLog, verify, _setForTests } from "./history";
import { exportLog, importLog } from "./history-io";

const base = {
  case_id: "case-01", title: "Test", entity: "Store 1, product 2", action: "approved" as const,
  validator_outcome: "recommend" as const, orders: [1, 0, 0], expected_cost: 10, cvar: 12, assumptions: {}, note: "",
};

describe("decision log", () => {
  beforeEach(() => resetLog());

  it("chains entries and detects edits", async () => {
    const a = await append(base);
    const b = await append({ ...base, note: "second" });
    expect(b.prev_hash).toBe(a.hash);
    expect((await verify([a, b])).ok).toBe(true);
    expect((await verify([{ ...a, note: "edited" }, b])).ok).toBe(false);
    expect((await verify([b])).ok).toBe(false);
  });

  it("round-trips export and import, and rejects tampered or oversized files", async () => {
    const a = await append(base);
    const text = exportLog([a]);
    resetLog();
    expect(await importLog(text)).toEqual({ ok: true, count: 1 });
    const tampered = text.replace('"expected_cost": 10', '"expected_cost": 1');
    expect((await importLog(tampered)).ok).toBe(false);
    expect((await importLog("{not json")).ok).toBe(false);
    expect((await importLog("x".repeat(1_000_001))).ok).toBe(false);
    _setForTests([]);
  });

  it("authenticates scenario assumptions and serializes concurrent records", async () => {
    const [a, b] = await Promise.all([append({ ...base, assumptions: { demand_shift: 0.1 } }), append(base)]);
    expect((await verify([a, b])).ok).toBe(true);
    expect((await verify([{ ...a, assumptions: { demand_shift: 0.2 } }, b])).ok).toBe(false);
  });
});
