import type { Alternative, DecisionCase, Terms } from "../engine/types";
import { money, pct, units } from "../lib/format";
import { RangeBar } from "./charts";

const NAMES = ["primary", "alternate", "expedite"];
const SUPPLIER_LABEL: Record<string, string> = { primary: "Primary supplier", alternate: "Alternate supplier", expedite: "Expedited freight" };

export function ordersText(o: number[]): string {
  const parts = o.map((q, i) => (q > 1e-6 ? `${units(q)} ${NAMES[i]}` : "")).filter(Boolean);
  return parts.length ? parts.join(", ") : "No order";
}

export function OrderLines({ orders, deliverable, late }: { orders: number[]; deliverable?: number[]; late?: number }) {
  const rows = orders.map((q, i) => [q, i] as const).filter(([q]) => q > 1e-6);
  if (!rows.length) return <span className="order-lines">No order</span>;
  return (
    <span className="order-lines">
      {rows.map(([q, i]) => (
        <span key={i}>
          {units(q)} {NAMES[i]}
          {deliverable && deliverable[i] < q - 1e-6 && <span className="late"> ({units(deliverable[i])} deliverable)</span>}
        </span>
      ))}
      {late !== undefined && late > 1e-6 && <span className="late">{units(late)} arrive after the horizon</span>}
    </span>
  );
}

const USES_PROPOSAL = new Set(["act_now", "wait", "escalate"]);

export function AlternativesTable({ alts, selected, onSelect, caption, proposed, isFeasible }: { alts: Alternative[]; selected: string; onSelect: (k: string) => void; caption?: string; proposed?: number[]; isFeasible?: (a: Alternative) => boolean }) {
  const lo = Math.min(...alts.map((a) => a.expected_cost));
  const hi = Math.max(...alts.map((a) => a.cvar));
  const best = alts.filter((a) => isFeasible?.(a) ?? true).reduce<Alternative | undefined>((b, a) => (!b || a.expected_cost < b.expected_cost ? a : b), undefined);
  return (
    <div className="table-wrap">
      <table className="data stack-sm">
        <thead>
          <tr>
            <th scope="col">Option</th>
            <th scope="col">Order</th>
            <th scope="col" className="r">Expected cost</th>
            <th scope="col" className="r">Worst 10% avg</th>
            <th scope="col" className="r">Fill rate</th>
          </tr>
        </thead>
        <tbody>
          {alts.map((a) => (
            <tr key={a.key} className={`clickable${a.key === selected ? " selected" : ""}`} onClick={() => onSelect(a.key)}
              aria-selected={a.key === selected}>
              <th scope="row" className="rowhead">
                <button className="btn quiet sm" style={{ padding: 0 }} onClick={(e) => { e.stopPropagation(); onSelect(a.key); }}>
                  {a.label}
                </button>
                {a.key === best?.key && <span className="tag" style={{ marginLeft: 6 }}>Lowest expected</span>}
                {isFeasible && !isFeasible(a) && <span className="tag" style={{ marginLeft: 6 }}>Submission blocked</span>}
              </th>
              <td className="full" data-label="Order">
                {proposed && USES_PROPOSAL.has(a.key)
                  ? <OrderLines orders={proposed} deliverable={a.orders} late={a.arrives_after_horizon} />
                  : <OrderLines orders={a.orders} late={a.arrives_after_horizon} />}
              </td>
              <td className="r num" data-label="Expected cost">{money(a.expected_cost)}{a.key !== "act_now" && <div className="xs faint">{money(a.delta_vs_act_now, { signed: true })}</div>}</td>
              <td className="r num" data-label="Worst 10% avg">{money(a.cvar)}<div className="option-spread"><RangeBar expected={a.expected_cost} cvar={a.cvar} p90={a.p90} domain={[lo, hi]} width={86} /></div></td>
              <td className="r num" data-label="Fill rate">{pct(a.expected_fill_rate, 1)}</td>
            </tr>
          ))}
        </tbody>
        {caption && <caption>{caption}</caption>}
      </table>
    </div>
  );
}

export function TermsTable({ plan, current }: { plan: Terms; current: Terms }) {
  const byPlan = new Map(plan.resources.map((r) => [r.name, r]));
  const diff = (a: unknown, b: unknown) => (a !== b ? { background: "var(--citrine-soft)", fontWeight: 600 } : undefined);
  return (
    <div className="table-wrap">
      <table className="data stack-sm">
        <thead>
          <tr>
            <th scope="col">Source</th>
            <th scope="col" className="r">Lead</th>
            <th scope="col" className="r">Unit cost</th>
            <th scope="col" className="r">Capacity</th>
            <th scope="col" className="r">Minimum</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {current.resources.map((r) => {
            const p = byPlan.get(r.name);
            const status = !r.eligible ? "Not qualified" : !r.available ? "Unavailable" : "Active";
            const pStatus = p ? (!p.eligible ? "Not qualified" : !p.available ? "Unavailable" : "Active") : status;
            return (
              <tr key={r.name}>
                <th scope="row" className="rowhead">{SUPPLIER_LABEL[r.name] ?? r.name}</th>
                <td className="r num" data-label="Lead" style={diff(p?.lead_days, r.lead_days)}>{r.lead_days === 0 ? "same day" : `${r.lead_days} d`}</td>
                <td className="r num" data-label="Unit cost" style={diff(p?.unit_cost.toFixed(4), r.unit_cost.toFixed(4))}>{money(r.unit_cost)}</td>
                <td className="r num" data-label="Capacity" style={diff(p?.capacity.toFixed(3), r.capacity.toFixed(3))}>{units(r.capacity)}</td>
                <td className="r num" data-label="Minimum">{r.min_quantity > 0 ? units(r.min_quantity) : "none"}</td>
                <td data-label="Status" style={diff(pStatus, status)}>{status}{pStatus !== status && <span className="xs faint"> (plan: {pStatus.toLowerCase()})</span>}</td>
              </tr>
            );
          })}
        </tbody>
        <caption>Current terms of record. Highlighted cells differ from the terms the planning system used. Budget {money(current.budget)}{plan.budget !== current.budget ? ` (plan assumed ${money(plan.budget)})` : ""}.</caption>
      </table>
    </div>
  );
}

export function caseLocation(c: DecisionCase): string {
  return `Store ${c.entity.store}, product ${c.entity.product}`;
}
