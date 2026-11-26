import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { BookOpen, ClipboardCheck, Database, FlaskConical, History, LayoutList, Menu, SlidersHorizontal, X } from "lucide-react";
import { useData, type Meta } from "../data/load";
import { useLog } from "../state/history";

const NAV = [
  { group: "Decisions", items: [
    { to: "/", label: "Overview", icon: LayoutList, end: true },
    { to: "/decisions", label: "Decision workspace", icon: ClipboardCheck },
    { to: "/studio", label: "Scenario studio", icon: SlidersHorizontal },
    { to: "/history", label: "Decision history", icon: History, count: true },
  ] },
  { group: "Evidence", items: [
    { to: "/benchmark", label: "Benchmark", icon: FlaskConical },
    { to: "/data", label: "Data and reliability", icon: Database },
    { to: "/methodology", label: "Methodology", icon: BookOpen },
  ] },
];

const TITLES: Record<string, string> = {
  "": "Overview",
  decisions: "Decision workspace",
  studio: "Scenario studio",
  history: "Decision history",
  benchmark: "Benchmark",
  data: "Data and reliability",
  methodology: "Methodology",
};

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#2742c4" />
      <path d="M9 9h14M9 16h9M9 23h14" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <circle cx="23" cy="16" r="2.6" fill="#e3b341" />
    </svg>
  );
}

/**
 * Tables that scroll sideways must be reachable by keyboard (WCAG 2.1.1). Only wrappers that actually
 * overflow get a tab stop, so wide screens do not gain pointless focus targets.
 */
function useFocusableScrollRegions() {
  useEffect(() => {
    const main = document.getElementById("main");
    if (!main) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        main.querySelectorAll<HTMLElement>(".table-wrap").forEach((el) => {
          if (el.scrollWidth > el.clientWidth + 1) {
            el.tabIndex = 0;
            el.setAttribute("role", "region");
            const heading = el.closest("section, .panel")?.querySelector("h2, h3")?.textContent;
            el.setAttribute("aria-label", heading ? `${heading} (scrolls sideways)` : "Table (scrolls sideways)");
          } else if (el.hasAttribute("tabindex")) {
            el.removeAttribute("tabindex");
            el.removeAttribute("role");
            el.removeAttribute("aria-label");
          }
        });
      });
    };
    const mo = new MutationObserver(update);
    mo.observe(main, { childList: true, subtree: true });
    window.addEventListener("resize", update);
    update();
    return () => {
      mo.disconnect();
      window.removeEventListener("resize", update);
      cancelAnimationFrame(frame);
    };
  }, []);
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const meta = useData<Meta>("meta");
  useFocusableScrollRegions();
  const log = useLog();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    const seg = loc.pathname.split("/")[1] ?? "";
    document.title = `${TITLES[seg] ?? "Not found"} | Enterprise Decision Intelligence`;
  }, [loc.pathname]);
  const synthetic = meta.status === "ready" && meta.data.data_source === "synthetic_fixture";
  const evidencePage = ["/benchmark", "/data", "/methodology"].includes(loc.pathname);
  return (
    <div className="shell">
      <a href="#main" className="sr-only skip">Skip to content</a>
      <aside className={`rail${open ? " open" : ""}`} aria-label="Primary">
        <NavLink to="/" className="brand">
          <BrandMark />
          <span>
            <span className="brand-name">Enterprise Decision Intelligence</span>
            <span className="brand-sub">Risk-aware decision validation</span>
          </span>
        </NavLink>
        <nav className="nav">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.end}>
                  <it.icon aria-hidden="true" />
                  {it.label}
                  {it.count && log.length > 0 && <span className="count">{log.length}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="rail-foot">
          {meta.status === "ready" ? (
            <>
              <div><strong>{meta.data.data_label}</strong></div>
              <div>Decision workspace demo</div>
            </>
          ) : (
            <div>Loading run details</div>
          )}
          <div style={{ marginTop: 8 }}>
            <a href="https://github.com/AbhinavVarma02" rel="noreferrer">Abhinav Varma Vathadi</a>
          </div>
        </div>
      </aside>
      {open && <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 30, background: "rgba(28,32,36,.25)" }} aria-hidden="true" />}
      <div className="main">
        <div className="topline">
          <button className="btn sm menu-btn" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"}>
            {open ? <X /> : <Menu />}
          </button>
          <span className="crumb">{TITLES[loc.pathname.split("/")[1] ?? ""] ?? "Not found"}</span>
          <span className="spacer" />
          {meta.status === "ready" && (
            <span className={`provenance${synthetic ? "" : " real"}`} title={meta.data.currency_note}>
              {evidencePage ? "Research and modeled assumptions" : synthetic ? "Synthetic decision cases" : "FreshRetailNet-50K with simulated operations"}
            </span>
          )}
        </div>
        <main id="main" className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
