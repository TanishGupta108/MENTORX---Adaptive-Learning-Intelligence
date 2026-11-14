/** Charts (Recharts). Only the student's own answers are drawn; predictions are never charted. */
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DayPoint } from "../api/tutor";
import { token } from "./ui";

const AXIS = { stroke: token("ink-faint"), fontSize: 12, tickLine: false, axisLine: false } as const;
const GRID = <CartesianGrid stroke={token("line")} strokeDasharray="3 4" vertical={false} />;
const tooltipStyle = {
  contentStyle: { background: "var(--color-surface-2)", border: "1px solid var(--color-line-strong)", borderRadius: 12, color: "var(--color-ink)", fontSize: 13 },
  labelStyle: { color: "var(--color-ink-muted)" },
  cursor: { fill: token("surface-3") },
};

function shortDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Questions answered per day (bars) and the share answered correctly (line). */
export function ActivityChart({ data, height = 240 }: { data: DayPoint[]; height?: number }) {
  const rows = data.map((d) => ({ ...d, label: shortDate(d.date), accuracyPct: d.accuracy === null ? null : Math.round(100 * d.accuracy) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        {GRID}
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={16} />
        <YAxis yAxisId="n" {...AXIS} allowDecimals={false} />
        <YAxis yAxisId="acc" orientation="right" domain={[0, 100]} {...AXIS} unit="%" />
        <Tooltip {...tooltipStyle} formatter={(v, name) => (name === "% correct" ? [`${v}%`, name] : [v, name])} />
        <Legend wrapperStyle={{ fontSize: 12, color: "var(--color-ink-muted)" }} iconType="circle" />
        <Bar yAxisId="n" dataKey="attempts" name="Questions answered" fill={token("brand")} radius={[6, 6, 0, 0]} maxBarSize={28} />
        <Line yAxisId="acc" type="monotone" dataKey="accuracyPct" name="% correct" stroke={token("strength")} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
