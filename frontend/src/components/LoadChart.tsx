// Detail chart: the last 60 min measured, the next 60 min forecast (line + band), and the capacity line.
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartPoint } from "../api/types";
import { formatClock, withZone } from "../lib/format";

export interface PlotPoint {
  t: number;
  load: number | null;
  server: number | null;
  expected: number | null;
  band: [number, number] | null;
}

/** Chart rows with numeric time and the forecast band as a [low, high] pair. */
export function toPlot(points: ChartPoint[]): PlotPoint[] {
  return points.map((p) => ({
    t: Date.parse(withZone(p.ts)),
    load: p.load,
    server: p.server,
    expected: p.expected,
    band: p.low !== null && p.high !== null ? [p.low, p.high] : null,
  }));
}

const fmt = (v: number) => (Math.round(v * 10) / 10).toString();

function TipBox({ active, payload }: { active?: boolean; payload?: { payload: PlotPoint }[] }) {
  const p = active && payload?.[0]?.payload;
  if (!p) return null;
  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-[var(--shadow-lift)]">
      <p className="font-medium text-ink">{new Date(p.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
      {p.load !== null && <p className="text-ink-soft">Group: {fmt(p.load)} servers' worth of work</p>}
      {p.server !== null && <p className="text-ink-soft">This server: {Math.round(p.server * 100)}% busy</p>}
      {p.expected !== null && <p className="text-ink-soft">Expected: {fmt(p.expected)} servers' worth</p>}
      {p.band && (
        <p className="text-muted">
          Likely between {fmt(p.band[0])} and {fmt(p.band[1])}
        </p>
      )}
    </div>
  );
}

function Key({ swatch, label }: { swatch: string; label: string }) {
  return (
    <li className="inline-flex items-center gap-1.5">
      <span className={swatch} aria-hidden />
      {label}
    </li>
  );
}

export function LoadChart({ points, capacity, now }: { points: ChartPoint[]; capacity: number; now: string }) {
  const data = toPlot(points);
  const nowT = Date.parse(withZone(now));
  const top = Math.max(capacity + 0.5, ...data.map((d) => Math.max(d.load ?? 0, d.band?.[1] ?? 0, d.expected ?? 0)));
  return (
    <figure>
      <div className="h-64 w-full sm:h-72" role="img" aria-label={`Load over the last and next 60 minutes. Capacity is ${capacity} servers.`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t: number) => formatClock(new Date(t).toISOString())}
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={[0, Math.ceil(top)]}
              allowDecimals={false}
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickLine={false}
              axisLine={false}
              width={40}
            />
            <Tooltip content={<TipBox />} />
            <Area dataKey="band" stroke="none" fill="#93c5fd" fillOpacity={0.3} isAnimationActive={false} connectNulls />
            <Line dataKey="load" stroke="#2563eb" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
            <Line dataKey="server" stroke="#94a3b8" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
            <Line
              dataKey="expected"
              stroke="#2563eb"
              strokeDasharray="5 4"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <ReferenceLine
              y={capacity}
              stroke="#dc2626"
              strokeDasharray="6 4"
              label={{ value: `Capacity: ${capacity} servers`, position: "insideTopLeft", fill: "#dc2626", fontSize: 11 }}
            />
            <ReferenceLine x={nowT} stroke="#94a3b8" label={{ value: "Now", position: "top", fill: "#64748b", fontSize: 11 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <Key swatch="h-0.5 w-4 bg-accent" label="Group work (1 = one server fully busy)" />
          <Key swatch="h-0.5 w-4 bg-slate-400" label="This server" />
          <Key swatch="h-0.5 w-4 border-t-2 border-dashed border-accent" label="Expected" />
          <Key swatch="h-2.5 w-4 rounded-sm bg-blue-300/40" label="Likely range" />
          <Key swatch="h-0.5 w-4 border-t-2 border-dashed border-red-600" label="Capacity" />
        </ul>
      </figcaption>
    </figure>
  );
}
