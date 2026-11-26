import type { ReactNode } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { Gate, GateStatus } from "../engine/types";
import { OUTCOME_LABEL } from "../lib/format";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="stack" style={{ gap: 12 }}>
      <span className="sr-only">{label}</span>
      <div className="skeleton" style={{ height: 34, width: "45%" }} />
      <div className="skeleton" style={{ height: 18, width: "70%" }} />
      <div className="skeleton" style={{ height: 220 }} />
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="panel state" role="alert">
      <h2>This view could not load its data</h2>
      <p>{message} The site serves precomputed files from /data; if you are running locally, run <code>edi export-web</code> first.</p>
      {retry && <button className="btn" onClick={retry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel state">
      <h2>{title}</h2>
      <p className="measure" style={{ margin: "0 auto" }}>{children}</p>
      {action}
    </div>
  );
}

export function OutcomeChip({ outcome }: { outcome: string }) {
  return <span className={`chip o-${outcome}`}>{OUTCOME_LABEL[outcome] ?? outcome}</span>;
}

const MARK: Record<GateStatus, ReactNode> = {
  pass: <Check aria-hidden="true" />,
  warn: <AlertTriangle aria-hidden="true" />,
  fail: <X aria-hidden="true" />,
};
const STATUS_WORD: Record<GateStatus, string> = { pass: "Passed", warn: "Warning", fail: "Failed" };

export function GateLedger({ gates }: { gates: Gate[] }) {
  return (
    <ol className="ledger" aria-label="Validation gates">
      {gates.map((g) => (
        <li key={g.gate}>
          <span className={`mark ${g.status}`} title={STATUS_WORD[g.status]}>
            {MARK[g.status]}
            <span className="sr-only">{STATUS_WORD[g.status]}</span>
          </span>
          <div>
            <div className="g-name"><span className="g-id">{g.gate}</span>{g.name}</div>
            <div className="g-sum">{g.summary}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Panel({ title, hint, children, pad = true, id }: { title?: ReactNode; hint?: ReactNode; children: ReactNode; pad?: boolean; id?: string }) {
  return (
    <section className="panel" aria-labelledby={id}>
      {title && (
        <div className="panel-head">
          <h2 id={id}>{title}</h2>
          {hint && <span className="hint">{hint}</span>}
        </div>
      )}
      <div className={pad ? "panel-pad" : undefined}>{children}</div>
    </section>
  );
}

export function NotFound() {
  return (
    <Empty title="Page not found" action={<Link className="btn" to="/">Go to the overview</Link>}>
      The address does not match any page in this workspace.
    </Empty>
  );
}
