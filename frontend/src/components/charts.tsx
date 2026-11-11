/**
 * Charts (Recharts). Observed accuracy and model predictions are always DIFFERENT series with
 * different marks and labels, so a prediction is never read as measured performance.
 */
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DayPoint, SkillSummary } from "../api/tutor";

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

/** Questions answered per day (bars) and observed accuracy (line). */
export function ActivityChart({ data, height = 240 }: { data: DayPoint[]; height?: number }) {
  const rows = data.map((d) => ({ ...d, label: shortDate(d.date), accuracyPct: d.accuracy === null ? null : Math.round(100 * d.accuracy) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        {GRID}
        <XAxis dataKey="label" {...AXIS} interval="preserveStartEnd" minTickGap={16} />
        <YAxis yAxisId="n" {...AXIS} allowDecimals={false} />
        <YAxis yAxisId="acc" orientation="right" domain={[0, 100]} {...AXIS} unit="%" />
        <Tooltip {...tooltipStyle} formatter={(v, name) => (name === "Observed accuracy" ? [`${v}%`, name] : [v, name])} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#9aa5c4" }} iconType="circle" />
        <Bar yAxisId="n" dataKey="attempts" name="Questions answered" fill="#8b8cff" radius={[6, 6, 0, 0]} maxBarSize={28} opacity={0.85} />
        <Line yAxisId="acc" type="monotone" dataKey="accuracyPct" name="Observed accuracy" stroke="#34d399" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Per skill: what the student actually got right vs what the model predicts. */
export function SkillComparisonChart({ skills, height }: { skills: SkillSummary[]; height?: number }) {
  const rows = skills.slice(0, 10).map((s) => ({
    name: s.code,
    full: s.name,
    observed: s.observed_accuracy === null ? null : Math.round(100 * s.observed_accuracy),
    model: s.predicted_p === null ? null : Math.round(100 * s.predicted_p),
  }));
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(220, rows.length * 44)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }} barGap={3}>
        <CartesianGrid stroke="#253150" strokeDasharray="3 4" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} unit="%" {...AXIS} />
        <YAxis type="category" dataKey="name" width={84} {...AXIS} />
        <Tooltip
          {...tooltipStyle}
          labelFormatter={(_, p) => (p?.[0]?.payload as { full?: string } | undefined)?.full ?? ""}
          formatter={(v, name) => [v === null ? "—" : `${v}%`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: "#9aa5c4" }} iconType="circle" />
        <Bar dataKey="observed" name="Observed accuracy (your answers)" fill="#34d399" radius={[0, 6, 6, 0]} maxBarSize={14} />
        <Bar dataKey="model" name="Model estimate (prediction)" fill="#5aa9ff" fillOpacity={0.45} stroke="#5aa9ff" strokeDasharray="4 3" radius={[0, 6, 6, 0]} maxBarSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Accuracy of each completed assessment/practice in order (observed only). */
export function TimelineChart({ points, height = 220 }: { points: { label: string; accuracy: number; kind: string }[]; height?: number }) {
  const rows = points.map((p, i) => ({ ...p, idx: i + 1, pct: Math.round(100 * p.accuracy) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
        {GRID}
        <XAxis dataKey="idx" {...AXIS} />
        <YAxis domain={[0, 100]} unit="%" {...AXIS} />
        <Tooltip {...tooltipStyle} labelFormatter={(_, p) => (p?.[0]?.payload as { label?: string } | undefined)?.label ?? ""} formatter={(v) => [`${v}%`, "Observed accuracy"]} />
        <Line type="monotone" dataKey="pct" name="Observed accuracy" stroke="#8b8cff" strokeWidth={2.5} dot={{ r: 4, fill: "#8b8cff" }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
