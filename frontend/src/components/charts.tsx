/** Charts (Recharts). Only the student's own answers are drawn; predictions are never charted. */
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DayPoint } from "../api/tutor";

const AXIS = { stroke: "#6b7697", fontSize: 12, tickLine: false, axisLine: false } as const;
const GRID = <CartesianGrid stroke="#253150" strokeDasharray="3 4" vertical={false} />;
const tooltipStyle = {
  contentStyle: { background: "#172036", border: "1px solid #33416a", borderRadius: 12, color: "#e8ebf5", fontSize: 13 },
  labelStyle: { color: "#9aa5c4" },
  cursor: { fill: "#8b8cff14" },
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
        <Legend wrapperStyle={{ fontSize: 12, color: "#9aa5c4" }} iconType="circle" />
        <Bar yAxisId="n" dataKey="attempts" name="Questions answered" fill="#8b8cff" radius={[6, 6, 0, 0]} maxBarSize={28} opacity={0.85} />
        <Line yAxisId="acc" type="monotone" dataKey="accuracyPct" name="% correct" stroke="#34d399" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
