/**
 * FR-DASH-02: the concept mastery map, laid out as the prerequisite graph.
 * Each concept sits one level below its deepest prerequisite; colour = mastery band.
 */
import type { Concept } from "../api/types";
import { cx, masteryTone, pct } from "./ui";

export function depths(concepts: Concept[]): Record<string, number> {
  const byCode = Object.fromEntries(concepts.map((c) => [c.code, c]));
  const memo: Record<string, number> = {};
  const depth = (code: string, seen: Set<string>): number => {
    if (code in memo) return memo[code]!;
    if (seen.has(code)) throw new Error(`prerequisite cycle at ${code}`);
    seen.add(code);
    const pre = byCode[code]?.prerequisites.filter((p) => p in byCode) ?? [];
    const d = pre.length ? 1 + Math.max(...pre.map((p) => depth(p, seen))) : 0;
    seen.delete(code);
    memo[code] = d;
    return d;
  };
  for (const c of concepts) depth(c.code, new Set());
  return memo;
}

const FILL: Record<ReturnType<typeof masteryTone>, string> = {
  mastered: "fill-success/15 stroke-success",
  ok: "fill-brand/15 stroke-brand",
  weak: "fill-warning/15 stroke-warning",
  low: "fill-danger/15 stroke-danger",
  unknown: "fill-surface stroke-line",
};

export const LEGEND: { tone: ReturnType<typeof masteryTone>; label: string }[] = [
  { tone: "mastered", label: "Mastered (≥ 80%)" },
  { tone: "ok", label: "In place (60–79%)" },
  { tone: "weak", label: "Weak (40–59%)" },
  { tone: "low", label: "Low (< 40%)" },
  { tone: "unknown", label: "Not assessed" },
];

export function ConceptMap({
  concepts,
  selected,
  onSelect,
}: {
  concepts: Concept[];
  selected?: string;
  onSelect: (code: string) => void;
}) {
  const d = depths(concepts);
  const levels: Concept[][] = [];
  for (const c of concepts) (levels[d[c.code]!] ??= []).push(c);
  const NODE_W = 150;
  const NODE_H = 46;
  const GAP_X = 16;
  const GAP_Y = 44;
  const widest = Math.max(...levels.map((l) => l.length));
  const W = widest * (NODE_W + GAP_X);
  const H = levels.length * (NODE_H + GAP_Y);
  const pos: Record<string, { x: number; y: number }> = {};
  levels.forEach((row, li) => {
    const rowW = row.length * (NODE_W + GAP_X) - GAP_X;
    row.forEach((c, i) => {
      pos[c.code] = { x: (W - rowW) / 2 + i * (NODE_W + GAP_X), y: li * (NODE_H + GAP_Y) + 4 };
    });
  });

  return (
    <div className="overflow-x-auto">
      <svg
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="mx-auto"
        role="group"
        aria-label="Concept map: prerequisites point down to the concepts that build on them"
      >
        {concepts.flatMap((c) =>
          c.prerequisites
            .filter((p) => pos[p])
            .map((p) => {
              const a = pos[p]!;
              const b = pos[c.code]!;
              const highlighted = selected === c.code || selected === p;
              return (
                <path
                  key={`${p}->${c.code}`}
                  d={`M${a.x + NODE_W / 2},${a.y + NODE_H} C${a.x + NODE_W / 2},${a.y + NODE_H + GAP_Y / 2} ${b.x + NODE_W / 2},${b.y - GAP_Y / 2} ${b.x + NODE_W / 2},${b.y}`}
                  fill="none"
                  className={highlighted ? "stroke-brand" : "stroke-line"}
                  strokeWidth={highlighted ? 2 : 1.25}
                />
              );
            }),
        )}
        {concepts.map((c) => {
          const p = pos[c.code]!;
          const tone = masteryTone(c.mastery);
          return (
            <g
              key={c.code}
              transform={`translate(${p.x},${p.y})`}
              role="button"
              tabIndex={0}
              aria-pressed={selected === c.code}
              aria-label={`${c.name}: ${c.mastery == null ? "not assessed yet" : `mastery ${pct(c.mastery)}`}`}
              className="cursor-pointer outline-none [&:focus-visible>rect]:stroke-[3]"
              onClick={() => onSelect(c.code)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(c.code);
                }
              }}
            >
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={8}
                className={cx(FILL[tone])}
                strokeWidth={selected === c.code ? 3 : 1.5}
              />
              <text x={10} y={19} className="fill-ink text-[12px] font-medium">
                {c.name.length > 22 ? `${c.name.slice(0, 21)}…` : c.name}
              </text>
              <text x={10} y={36} className="fill-ink-muted text-[11px]">
                {c.mastery == null ? "not assessed" : pct(c.mastery)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
