/**
 * Small hand-written SVG charts (no chart library keeps the bundle small, NFR-PERF-03).
 * Every value comes from the API; days without data are gaps, never zeros (FR-DASH-08).
 */
import type { Activity, Trends } from "../api/types";
import { pct } from "./ui";

const W = 640;
const H = 200;
const PAD = { l: 36, r: 12, t: 12, b: 28 };

/** Split a series into runs of consecutive non-null values (gaps stay gaps). */
export function segments(values: (number | null)[]): { i: number; v: number }[][] {
  const out: { i: number; v: number }[][] = [];
  let cur: { i: number; v: number }[] = [];
  values.forEach((v, i) => {
    if (v == null) {
      if (cur.length) out.push(cur);
      cur = [];
    } else cur.push({ i, v });
  });
  if (cur.length) out.push(cur);
  return out;
}

function shortDate(iso: string) {
  const [, m, d] = iso.split("-").map(Number);
  return new Date(2000, (m ?? 1) - 1, d ?? 1).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export function TrendChart({ trends }: { trends: Trends }) {
  const pts = trends.points;
  const n = pts.length;
  const x = (i: number) => PAD.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - PAD.l - PAD.r));
  const y = (v: number) => PAD.t + (1 - v) * (H - PAD.t - PAD.b);
  const series = [
    { key: "mean_mastery" as const, label: "Mean mastery", cls: "stroke-brand fill-brand" },
    { key: "accuracy" as const, label: "Accuracy that day", cls: "stroke-success fill-success" },
  ];
  const first = pts[0];
  const last = pts[n - 1];

  return (
    <figure>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Mean mastery and daily accuracy over the last ${trends.days} days`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" className="fill-ink-muted text-[11px]">
              {v * 100}%
            </text>
          </g>
        ))}
        {series.map((s) =>
          segments(pts.map((p) => p[s.key])).map((seg, k) =>
            seg.length === 1 ? (
              <circle key={`${s.key}${k}`} cx={x(seg[0]!.i)} cy={y(seg[0]!.v)} r={3} className={s.cls} />
            ) : (
              <polyline
                key={`${s.key}${k}`}
                points={seg.map((p) => `${x(p.i)},${y(p.v)}`).join(" ")}
                fill="none"
                strokeWidth={2.5}
                strokeLinejoin="round"
                className={s.cls.split(" ")[0]}
              />
            ),
          ),
        )}
        {first && (
          <text x={PAD.l} y={H - 8} className="fill-ink-muted text-[11px]">
            {shortDate(first.day)}
          </text>
        )}
        {last && (
          <text x={W - PAD.r} y={H - 8} textAnchor="end" className="fill-ink-muted text-[11px]">
            {shortDate(last.day)}
          </text>
        )}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-ink-muted">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className={`inline-block h-0.5 w-4 ${s.cls.includes("brand") ? "bg-brand" : "bg-success"}`} />
            {s.label}
          </span>
        ))}
      </figcaption>
      {/* Screen-reader table with the same data. */}
      <table className="sr-only">
        <caption>Daily answers, accuracy and mean mastery</caption>
        <thead>
          <tr>
            <th>Day</th>
            <th>Answered</th>
            <th>Accuracy</th>
            <th>Mean mastery</th>
          </tr>
        </thead>
        <tbody>
          {pts
            .filter((p) => p.answered > 0)
            .map((p) => (
              <tr key={p.day}>
                <td>{p.day}</td>
                <td>{p.answered}</td>
                <td>{p.accuracy == null ? "—" : pct(p.accuracy)}</td>
                <td>{p.mean_mastery == null ? "—" : pct(p.mean_mastery)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Bucket a day's count into 0–4 for colour intensity, relative to the busiest day. */
export function level(count: number, max: number) {
  if (count <= 0 || max <= 0) return 0;
  return Math.min(4, Math.ceil((count / max) * 4));
}

const LEVEL_OPACITY = [0, 0.25, 0.5, 0.75, 1];

export function ActivityHeatmap({ activity }: { activity: Activity }) {
  const days = activity.days;
  const max = Math.max(0, ...days.map((d) => d.answered));
  const cell = 12;
  const gap = 3;
  // Columns are weeks ending today; the first column may be partial.
  const cols = Math.ceil(days.length / 7);
  const offset = cols * 7 - days.length;
  const total = days.reduce((s, d) => s + d.answered, 0);
  const active = days.filter((d) => d.answered > 0).length;

  return (
    <figure>
      <div className="overflow-x-auto">
        <svg
          width={cols * (cell + gap)}
          height={7 * (cell + gap)}
          role="img"
          aria-label={`${total} questions answered on ${active} of the last ${days.length} days`}
        >
          {days.map((d, i) => {
            const j = i + offset;
            const lv = level(d.answered, max);
            return (
              <rect
                key={d.day}
                x={Math.floor(j / 7) * (cell + gap)}
                y={(j % 7) * (cell + gap)}
                width={cell}
                height={cell}
                rx={2}
                className={lv ? "fill-brand" : "fill-line"}
                fillOpacity={lv ? LEVEL_OPACITY[lv] : 1}
              >
                <title>{`${d.day}: ${d.answered} answered`}</title>
              </rect>
            );
          })}
        </svg>
      </div>
      <figcaption className="mt-2 text-xs text-ink-muted">
        {total} questions on {active} day{active === 1 ? "" : "s"} in the last {activity.weeks} weeks
        ({activity.timezone} time)
      </figcaption>
    </figure>
  );
}
