/** Small, purpose-built SVG charts. Each answers one question; none is decorative. */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { scaleBand, scaleLinear } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import type { FanPoint } from "../engine/types";
import { money, units } from "../lib/format";

const COBALT = "#2742c4";
const CITRINE = "#e3b341";
const INK3 = "#5f6872";

/** Width of the chart's container in CSS pixels, so text in the SVG renders at its real size on every screen. */
function useWidth(fallback: number): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const cw = Math.round(el.clientWidth);
      if (cw > 0) setW((prev) => (Math.abs(prev - cw) > 1 ? cw : prev));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Nudges point labels down until they stop overlapping. Approximate text width; good enough for a handful of labels. */
function placeLabels(items: { x: number; y: number; text: string; anchor: "start" | "end" }[]): number[] {
  const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const order = items.map((_, i) => i).sort((a, b) => items[a].y - items[b].y);
  const ys = items.map((it) => it.y);
  for (const i of order) {
    const it = items[i];
    const w = it.text.length * 6.3;
    const x0 = it.anchor === "start" ? it.x : it.x - w;
    let y = it.y;
    for (let k = 0; k < 8; k++) {
      const hit = placed.some((b) => x0 < b.x1 && x0 + w > b.x0 && y - 11 < b.y1 && y + 2 > b.y0);
      if (!hit) break;
      y += 13;
    }
    ys[i] = y;
    placed.push({ x0, x1: x0 + w, y0: y - 11, y1: y + 2 });
  }
  return ys;
}

export function RangeBar({ expected, cvar, p90, domain, width = 150 }: { expected: number; cvar: number; p90: number; domain: [number, number]; width?: number }) {
  const x = scaleLinear().domain(domain).range([6, width - 6]).clamp(true);
  return (
    <svg width={width} height={18} role="img" aria-label={`Expected ${money(expected)}, 90th percentile ${money(p90)}, tail average ${money(cvar)}`}>
      <line x1={6} x2={width - 6} y1={9} y2={9} stroke="#e9ecee" strokeWidth={6} strokeLinecap="round" />
      <line x1={x(expected)} x2={x(cvar)} y1={9} y2={9} stroke="#c4ccf2" strokeWidth={6} strokeLinecap="round" />
      <line x1={x(p90)} x2={x(p90)} y1={3} y2={15} stroke={INK3} strokeWidth={1.5} />
      <circle cx={x(expected)} cy={9} r={4.5} fill={COBALT} />
      <line x1={x(cvar)} x2={x(cvar)} y1={2} y2={16} stroke="#b3261e" strokeWidth={2} />
    </svg>
  );
}

export function FanChart({ fan, dates, height = 200, onHand }: { fan: FanPoint[]; dates: string[]; height?: number; onHand?: number }) {
  const width = 330;
  const m = { t: 14, r: 34, b: 28, l: 34 };
  const x = scaleLinear().domain([0, fan.length - 1]).range([m.l, width - m.r]);
  const ymax = Math.max(...fan.map((f) => f.p95), onHand ?? 0) * 1.1 || 1;
  const y = scaleLinear().domain([0, ymax]).nice().range([height - m.b, m.t]);
  const outer = area<FanPoint>().x((d) => x(d.day)).y0((d) => y(d.p5)).y1((d) => y(d.p95)).curve(curveMonotoneX)(fan) ?? "";
  const inner = area<FanPoint>().x((d) => x(d.day)).y0((d) => y(d.p25)).y1((d) => y(d.p75)).curve(curveMonotoneX)(fan) ?? "";
  const med = line<FanPoint>().x((d) => x(d.day)).y((d) => y(d.p50)).curve(curveMonotoneX)(fan) ?? "";
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Demand forecast range for the next three days">
        {y.ticks(4).map((t) => (
          <g key={t}>
            <line className="gridline" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} />
            <text x={m.l - 8} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        <path d={outer} fill="#e8ecfb" />
        <path d={inner} fill="#c4ccf2" />
        <path d={med} fill="none" stroke={COBALT} strokeWidth={2} />
        {fan.map((f) => <circle key={f.day} cx={x(f.day)} cy={y(f.p50)} r={3} fill={COBALT} />)}
        {onHand !== undefined && (
          <g>
            <line x1={m.l} x2={width - m.r} y1={y(onHand)} y2={y(onHand)} stroke={CITRINE} strokeDasharray="4 3" strokeWidth={1.5} />
            <text x={width - m.r} y={y(onHand) - 5} textAnchor="end" style={{ fill: "#6d5100" }}>on hand {units(onHand)}</text>
          </g>
        )}
        {fan.map((f, i) => <text key={f.day} x={x(f.day)} y={height - 8} textAnchor="middle">{dates[i] ?? `+${f.day}`}</text>)}
      </svg>
      <figcaption className="chart-legend" style={{ marginTop: 4 }}>
        <span><i style={{ background: COBALT }} />Median</span>
        <span><i style={{ background: "#c4ccf2", height: 8 }} />50% range</span>
        <span><i style={{ background: "#e8ecfb", height: 8 }} />90% range</span>
      </figcaption>
    </figure>
  );
}

export function InventoryBars({ recorded, verified, labels }: { recorded: number[]; verified: number[]; labels: string[] }) {
  const width = 330;
  const height = 170;
  const m = { t: 10, r: 8, b: 26, l: 34 };
  const x0 = scaleBand<number>().domain(recorded.map((_, i) => i)).range([m.l, width - m.r]).padding(0.3);
  const x1 = scaleBand<string>().domain(["rec", "ver"]).range([0, x0.bandwidth()]).padding(0.1);
  const y = scaleLinear().domain([0, Math.max(1, ...recorded, ...verified) * 1.1]).nice().range([height - m.b, m.t]);
  const differs = recorded.some((r, i) => Math.abs(r - verified[i]) > 1e-6);
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="On-hand stock by age, recorded versus verified">
        {y.ticks(3).map((t) => (
          <g key={t}>
            <line className="gridline" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} />
            <text x={m.l - 8} y={y(t) + 4} textAnchor="end">{t}</text>
          </g>
        ))}
        {recorded.map((r, i) => (
          <g key={i} transform={`translate(${x0(i)},0)`}>
            <rect x={x1("rec")} width={x1.bandwidth()} y={y(r)} height={y(0) - y(r)} fill={COBALT} rx={2} />
            <rect x={x1("ver")} width={x1.bandwidth()} y={y(verified[i])} height={y(0) - y(verified[i])} fill={differs ? CITRINE : "#c4ccf2"} rx={2} />
            <text x={x0.bandwidth() / 2} y={height - 8} textAnchor="middle">{labels[i]}</text>
          </g>
        ))}
      </svg>
      <figcaption className="chart-legend">
        <span><i style={{ background: COBALT, height: 8 }} />Recorded in system</span>
        <span><i style={{ background: differs ? CITRINE : "#c4ccf2", height: 8 }} />Physically present (simulator truth)</span>
      </figcaption>
    </figure>
  );
}

export interface DotRow {
  label: string;
  mean: number;
  lo: number;
  hi: number;
  emphasis?: "ours" | "ref" | "oracle";
  note?: string;
}

export function DotWhisker({ rows, format = money, ariaLabel, refValue, xLabel }: { rows: DotRow[]; format?: (x: number) => string; ariaLabel: string; refValue?: number; xLabel?: string }) {
  const [ref, width] = useWidth(640);
  // Below ~520 px the labels move above their row instead of sitting in a left column.
  const narrow = width < 520;
  const rowH = narrow ? 42 : 30;
  const m = narrow ? { t: 8, r: 62, b: 30, l: 10 } : { t: 8, r: 72, b: 30, l: Math.min(210, Math.round(width * 0.34)) };
  const height = m.t + m.b + rows.length * rowH + (xLabel ? 14 : 0);
  const lo = Math.min(...rows.map((r) => r.lo), refValue ?? Infinity);
  const hi = Math.max(...rows.map((r) => r.hi), refValue ?? -Infinity);
  const pad = (hi - lo) * 0.08 || 1;
  const x = scaleLinear().domain([lo - pad, hi + pad]).nice().range([m.l, width - m.r]);
  const plotBottom = m.t + rows.length * rowH;
  return (
    <div ref={ref} className="chart-box">
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={ariaLabel}>
        {x.ticks(narrow ? 4 : 5).map((t) => (
          <g key={t}>
            <line className="gridline" x1={x(t)} x2={x(t)} y1={m.t} y2={plotBottom} />
            <text x={x(t)} y={plotBottom + 18} textAnchor="middle">{format(t)}</text>
          </g>
        ))}
        {refValue !== undefined && <line x1={x(refValue)} x2={x(refValue)} y1={m.t} y2={plotBottom} stroke={INK3} strokeDasharray="3 3" />}
        {rows.map((r, i) => {
          const cy = narrow ? m.t + i * rowH + 28 : m.t + i * rowH + rowH / 2;
          const color = r.emphasis === "ours" ? COBALT : r.emphasis === "oracle" ? INK3 : "#4a535c";
          return (
            <g key={r.label}>
              <text x={narrow ? m.l : m.l - 12} y={narrow ? cy - 12 : cy + 4} textAnchor={narrow ? "start" : "end"}
                style={{ fill: "#1c2024", fontWeight: r.emphasis === "ours" ? 600 : 400 }}>{r.label}</text>
              <line x1={x(r.lo)} x2={x(r.hi)} y1={cy} y2={cy} stroke={color} strokeWidth={2} />
              <circle cx={x(r.mean)} cy={cy} r={5} fill={r.emphasis === "oracle" ? "#fff" : color} stroke={color} strokeWidth={2} />
              <text x={width - m.r + 8} y={cy + 4} style={{ fill: "#4a535c" }}>{format(r.mean)}</text>
            </g>
          );
        })}
        {xLabel && <text x={(m.l + width - m.r) / 2} y={height - 4} textAnchor="middle">{xLabel}</text>}
      </svg>
    </div>
  );
}

export function Scatter({ points, xLabel, xLabelShort, yLabel, ariaLabel, xFormat = (v: number) => v.toFixed(2), yFormat = money }: {
  points: { x: number; y: number; label: string; hollow?: boolean; highlight?: boolean }[];
  xLabel: string; xLabelShort?: string; yLabel: string; ariaLabel: string; xFormat?: (v: number) => string; yFormat?: (v: number) => string;
}) {
  const [ref, width] = useWidth(560);
  const narrow = width < 480;
  const height = narrow ? 280 : 300;
  const m = { t: 14, r: narrow ? 16 : 40, b: 44, l: 74 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = scaleLinear().domain([Math.min(...xs), Math.max(...xs)]).nice().range([m.l, width - m.r]);
  const y = scaleLinear().domain([Math.min(...ys), Math.max(...ys)]).nice().range([height - m.b, m.t]);
  const labels = points.map((p) => {
    const px = x(p.x);
    const w = p.label.length * 6.3;
    const fitsRight = px + 9 + w <= width - 4;
    const fitsLeft = px - 9 - w >= 4;
    const anchor: "start" | "end" = !fitsRight && fitsLeft ? "end" : "start";
    const lx = anchor === "end" ? px - 9 : Math.min(px + 9, width - 4 - w);
    return { x: lx, y: y(p.y) - 7, text: p.label, anchor };
  });
  const ly = placeLabels(labels);
  return (
    <div ref={ref} className="chart-box">
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={ariaLabel}>
      {x.ticks(narrow ? 4 : 5).map((t) => <g key={`x${t}`}><line className="gridline" x1={x(t)} x2={x(t)} y1={m.t} y2={height - m.b} /><text x={x(t)} y={height - m.b + 16} textAnchor="middle">{xFormat(t)}</text></g>)}
      {y.ticks(5).map((t) => <g key={`y${t}`}><line className="gridline" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} /><text x={m.l - 8} y={y(t) + 4} textAnchor="end">{yFormat(t)}</text></g>)}
      {points.map((p, i) => (
        <g key={p.label + (p.hollow ? "h" : "")}>
          <circle cx={x(p.x)} cy={y(p.y)} r={6} fill={p.hollow ? "#fff" : p.highlight ? COBALT : "#4a535c"} stroke={p.highlight ? COBALT : "#4a535c"} strokeWidth={2} />
          <text x={labels[i].x} y={ly[i]} textAnchor={labels[i].anchor} style={{ fill: "#1c2024", fontWeight: p.highlight ? 600 : 400 }}>{p.label}</text>
        </g>
      ))}
      <text x={(m.l + width - m.r) / 2} y={height - 6} textAnchor="middle">{narrow && xLabelShort ? xLabelShort : xLabel}</text>
      <text transform={`translate(14 ${(m.t + height - m.b) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
    </svg>
    </div>
  );
}

export function LineSeries({ series, xLabel, yLabel, ariaLabel, xFormat, yFormat, markers }: {
  series: { name: string; color: string; points: { x: number; y: number }[]; dashed?: boolean }[];
  xLabel: string; yLabel: string; ariaLabel: string; xFormat: (v: number) => string; yFormat: (v: number) => string;
  markers?: { x: number; label: string }[];
}) {
  const [ref, width] = useWidth(640);
  const narrow = width < 480;
  const height = 240;
  const m = { t: 14, r: 18, b: 44, l: 56 };
  const all = series.flatMap((s) => s.points);
  const x = scaleLinear().domain([Math.min(...all.map((p) => p.x)), Math.max(...all.map((p) => p.x))]).range([m.l, width - m.r]);
  const y = scaleLinear().domain([Math.min(0, ...all.map((p) => p.y)), Math.max(...all.map((p) => p.y)) * 1.05 || 1]).nice().range([height - m.b, m.t]);
  const id = useId();
  return (
    <figure ref={ref} style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={ariaLabel} aria-describedby={id}>
        {y.ticks(4).map((t) => <g key={t}><line className="gridline" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} /><text x={m.l - 8} y={y(t) + 4} textAnchor="end">{yFormat(t)}</text></g>)}
        {x.ticks(narrow ? 4 : 6).map((t) => <text key={t} x={x(t)} y={height - m.b + 16} textAnchor="middle">{xFormat(t)}</text>)}
        {markers?.map((mk) => (
          <g key={mk.label}>
            <line x1={x(mk.x)} x2={x(mk.x)} y1={m.t} y2={height - m.b} stroke={CITRINE} strokeWidth={1.5} />
            <text x={x(mk.x) + 4} y={m.t + 10} style={{ fill: "#6d5100" }}>{mk.label}</text>
          </g>
        ))}
        {series.map((s) => (
          <g key={s.name}>
            <path d={line<{ x: number; y: number }>().x((p) => x(p.x)).y((p) => y(p.y))(s.points) ?? ""} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} />
            {s.points.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r={3} fill={s.color} />)}
          </g>
        ))}
        <text x={(m.l + width - m.r) / 2} y={height - 6} textAnchor="middle">{xLabel}</text>
        <text transform={`translate(14 ${(m.t + height - m.b) / 2}) rotate(-90)`} textAnchor="middle">{yLabel}</text>
      </svg>
      <figcaption id={id} className="chart-legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</figcaption>
    </figure>
  );
}

export function Heatmap({ rows, cols, values, mark, candidate, rowLabel, colLabel, measure = "expected cost" }: {
  rows: number[]; cols: number[]; values: (number | null)[][]; mark?: [number, number]; candidate?: [number, number];
  rowLabel: string; colLabel: string; measure?: string;
}) {
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null);
  const flat = values.flat().filter((v): v is number => v !== null);
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const color = useMemo(() => scaleLinear<string>().domain([lo, lo + (hi - lo) * 0.25, hi]).range(["#1d3297", "#8d9ce6", "#f1f3fb"]).clamp(true), [lo, hi]);
  const cw = 46;
  const ch = 24;
  const m = { t: 8, l: 64, b: 40 };
  const width = m.l + cols.length * cw + 8;
  const height = m.t + rows.length * ch + m.b;
  const nearest = (arr: number[], v: number) => arr.reduce((b, x, k) => (Math.abs(x - v) < Math.abs(arr[b] - v) ? k : b), 0);
  return (
    <figure style={{ margin: 0, position: "relative" }}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" style={{ maxWidth: width * 1.4 }} role="img"
        aria-label={`${measure} over ${rowLabel} and ${colLabel}; darker is cheaper`} onMouseLeave={() => setHover(null)}>
        {rows.map((r, i) => (
          <g key={r}>
            <text x={m.l - 8} y={height - m.b - i * ch - ch / 2 + 4} textAnchor="end">{units(r, 0)}</text>
            {cols.map((c, j) => {
              const v = values[i][j];
              return (
                <rect key={c} x={m.l + j * cw} y={height - m.b - (i + 1) * ch} width={cw - 2} height={ch - 2} rx={2}
                  fill={v === null ? "#f5f6f4" : color(v)} onMouseEnter={() => setHover({ i, j })}>
                  <title>{v === null ? "Not allowed by budget" : `${units(r, 1)} primary, ${units(c, 1)} alternate: ${money(v)}`}</title>
                </rect>
              );
            })}
          </g>
        ))}
        {cols.map((c, j) => <text key={c} x={m.l + j * cw + cw / 2} y={height - m.b + 16} textAnchor="middle">{units(c, 0)}</text>)}
        {candidate && (() => {
          const i = nearest(rows, candidate[0]);
          const j = nearest(cols, candidate[1]);
          return <rect x={m.l + j * cw - 1} y={height - m.b - (i + 1) * ch - 1} width={cw} height={ch} fill="none" stroke="#1c2024" strokeDasharray="3 2" strokeWidth={1.5} rx={3} />;
        })()}
        {mark && (() => {
          const i = rows.indexOf(mark[0]);
          const j = cols.indexOf(mark[1]);
          if (i < 0 || j < 0) return null;
          return <rect x={m.l + j * cw - 1} y={height - m.b - (i + 1) * ch - 1} width={cw} height={ch} fill="none" stroke={CITRINE} strokeWidth={3} rx={3} />;
        })()}
        <text x={m.l + (cols.length * cw) / 2} y={height - 6} textAnchor="middle">{colLabel}</text>
        <text transform={`translate(12 ${(m.t + height - m.b) / 2}) rotate(-90)`} textAnchor="middle">{rowLabel}</text>
      </svg>
      <figcaption className="chart-legend" style={{ marginTop: 4 }}>
        <span><i style={{ background: "#1d3297", height: 8 }} />Lowest {measure} {money(lo)}</span>
        <span><i style={{ background: "#f1f3fb", height: 8, outline: "1px solid #dadfe3" }} />Highest {money(hi)}</span>
        <span><i style={{ background: CITRINE, height: 8 }} />Recommended</span>
        <span><i style={{ background: "#1c2024", height: 2 }} />System proposal</span>
        {hover && values[hover.i][hover.j] !== null && <span className="num">Hover: {units(rows[hover.i])} / {units(cols[hover.j])} costs {money(values[hover.i][hover.j])}</span>}
      </figcaption>
    </figure>
  );
}

export function DailySeries({ points, split, yFormat, ariaLabel }: { points: { x: number; y: number; label: string }[]; split?: number; yFormat: (v: number) => string; ariaLabel: string }) {
  const [ref, width] = useWidth(640);
  const height = 170;
  const m = { t: 10, r: 12, b: 28, l: 48 };
  const x = scaleLinear().domain([points[0].x, points[points.length - 1].x]).range([m.l, width - m.r]);
  const y = scaleLinear().domain([0, Math.max(...points.map((p) => p.y)) * 1.1 || 1]).nice().range([height - m.b, m.t]);
  const path = line<{ x: number; y: number }>().x((p) => x(p.x)).y((p) => y(p.y))(points) ?? "";
  const every = width < 480 ? 28 : 14;
  const ticks = points.filter((_, i) => i % every === 0);
  return (
    <div ref={ref} className="chart-box">
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={ariaLabel}>
      {y.ticks(3).map((t) => <g key={t}><line className="gridline" x1={m.l} x2={width - m.r} y1={y(t)} y2={y(t)} /><text x={m.l - 8} y={y(t) + 4} textAnchor="end">{yFormat(t)}</text></g>)}
      {split !== undefined && (
        <g>
          <rect x={x(split)} y={m.t} width={width - m.r - x(split)} height={height - m.b - m.t} fill="#fbf3dc" />
          <text x={x(split) - 6} y={m.t + 12} textAnchor="end" style={{ fill: "#6d5100" }}>Final test window</text>
        </g>
      )}
      <path d={path} fill="none" stroke={COBALT} strokeWidth={1.8} />
      {ticks.map((p) => <text key={p.x} x={x(p.x)} y={height - 8} textAnchor="middle">{p.label}</text>)}
    </svg>
    </div>
  );
}
