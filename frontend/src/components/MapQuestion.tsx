/**
 * Geography map questions, drawn with plain SVG.
 * - The base map (/maps/<map>.json) is a list of land outlines with no codes or names.
 * - The question carries only the geometry of its own regions: one highlighted region
 *   ("name the highlighted place") or four lettered candidates ("where is X?").
 * - Tapping a lettered region selects that option; the option buttons stay the keyboard path.
 * Nothing here knows which place is which, so the answer can't leak from the drawing.
 */
import { useEffect, useState } from "react";
import type { BaseMap, MapMedia, MapRegion } from "../api/tutor";
import { MAP_NOTICE } from "./Credits";
import { Button, cx } from "./ui";

const MAP_TITLES: Record<MapMedia["map"], string> = {
  europe: "Europe",
  africa: "Africa",
  samerica: "South America",
  namerica: "North America",
  oceania: "Oceania",
  us: "the United States",
};

const cache = new Map<string, Promise<BaseMap>>();

export function resetMapCache() {
  cache.clear();
}

function loadBaseMap(name: string): Promise<BaseMap> {
  let p = cache.get(name);
  if (!p) {
    p = fetch(`/maps/${encodeURIComponent(name)}.json`, { headers: { Accept: "application/json" } }).then((r) => {
      if (!r.ok) throw new Error(`map ${r.status}`);
      return r.json() as Promise<BaseMap>;
    });
    p.catch(() => cache.delete(name));
    cache.set(name, p);
  }
  return p;
}

function useBaseMap(name: string) {
  const [state, setState] = useState<{ map?: BaseMap; error?: boolean }>({});
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState({});
    loadBaseMap(name).then(
      (map) => alive && setState({ map }),
      () => alive && setState({ error: true }),
    );
    return () => {
      alive = false;
    };
  }, [name, tick]);
  return { ...state, retry: () => setTick((t) => t + 1) };
}

function parseViewBox(vb: string) {
  const [x = 0, y = 0, w = 100, h = 100] = vb.trim().split(/[\s,]+/).map(Number);
  return { x, y, w, h };
}

type Tone = "highlight" | "candidate" | "selected" | "correct" | "wrong" | "muted";

const TONE: Record<Tone, { fill: string; stroke: string; badge: string }> = {
  highlight: { fill: "fill-brand/75", stroke: "stroke-brand", badge: "fill-brand-strong" },
  candidate: { fill: "fill-brand/45", stroke: "stroke-brand", badge: "fill-brand-strong" },
  selected: { fill: "fill-brand/80", stroke: "stroke-white", badge: "fill-brand" },
  correct: { fill: "fill-strength/80", stroke: "stroke-strength", badge: "fill-strength" },
  wrong: { fill: "fill-weakness/80", stroke: "stroke-weakness", badge: "fill-weakness" },
  muted: { fill: "fill-brand/25", stroke: "stroke-line-strong", badge: "fill-surface-3" },
};

type Props = {
  media: MapMedia;
  /** Selected option id (= region label for "locate" questions). */
  selected?: string | null;
  onSelect?: (label: string) => void;
  disabled?: boolean;
  /** After answering: the correct option ids, and the student's pick. */
  correctIds?: string[];
  answered?: boolean;
  className?: string;
};

export function MapQuestion({ media, selected = null, onSelect, disabled, correctIds = [], answered = false, className }: Props) {
  const { map, error, retry } = useBaseMap(media.map);
  const title = MAP_TITLES[media.map] ?? "the map";

  const toneFor = (r: MapRegion): Tone => {
    if (r.label === null) return "highlight";
    if (answered) {
      if (correctIds.includes(r.label)) return "correct";
      if (r.label === selected) return "wrong";
      return "muted";
    }
    return r.label === selected ? "selected" : "candidate";
  };

  let body;
  if (error) {
    body = (
      <div className="flex aspect-[4/3] flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-surface-2 p-6 text-center text-sm text-ink-muted" role="alert">
        Couldn’t load the map.
        <Button variant="secondary" size="sm" onClick={retry}>
          Try again
        </Button>
      </div>
    );
  } else if (!map) {
    body = (
      <div className="grid aspect-[4/3] place-items-center rounded-2xl border border-line bg-surface-2 text-sm text-ink-muted" role="status">
        Loading the map…
      </div>
    );
  } else {
    const vb = parseViewBox(map.viewBox);
    // 1 % of the map's larger side: tall maps (South America, Africa) are drawn narrow, so sizing
    // by width alone would make the letters too small to read or tap on a phone.
    const unit = Math.max(vb.w, vb.h) / 100;
    const labelled = media.regions.filter((r) => r.label);
    // letter badges never overlap: at most a bit under half the gap between the closest two
    let minGap = Infinity;
    for (let i = 0; i < labelled.length; i++)
      for (let j = i + 1; j < labelled.length; j++) {
        const [x1, y1] = labelled[i]!.anchor;
        const [x2, y2] = labelled[j]!.anchor;
        minGap = Math.min(minGap, Math.hypot(x1 - x2, y1 - y2));
      }
    const badge = Math.min(3 * unit, Math.max(0.46 * minGap, 1.8 * unit));
    const clickable = Boolean(onSelect) && !disabled && !answered;
    const pick = (label: string | null) => {
      if (label && clickable) onSelect!(label);
    };
    body = (
      <svg viewBox={map.viewBox} preserveAspectRatio="xMidYMid meet" className="block h-auto max-h-[60vh] w-full rounded-2xl border border-line" role="img" aria-label={`Map of ${title}${labelled.length ? ` with ${media.regions.length} lettered places` : " with one highlighted place"}`}>
        <rect x={vb.x} y={vb.y} width={vb.w} height={vb.h} className="fill-surface-2" />
        <g className="fill-surface-3 stroke-line-strong" strokeWidth={0.75} vectorEffect="non-scaling-stroke">
          {map.land.map((d, i) => (
            <path key={i} d={d} vectorEffect="non-scaling-stroke" />
          ))}
        </g>
        {media.regions.map((r, i) => {
          const t = TONE[toneFor(r)];
          const [ax, ay] = r.anchor;
          return (
            <g key={r.label ?? i} data-region={r.label ?? "highlight"} onClick={() => pick(r.label)} className={cx(clickable && r.label && "cursor-pointer")}>
              {r.shape === "area" && <path d={r.d} className={cx(t.fill, t.stroke)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
              {r.shape === "line" && (
                <>
                  <path d={r.d} fill="none" stroke="transparent" strokeWidth={16} vectorEffect="non-scaling-stroke" />
                  <path d={r.d} fill="none" className={t.stroke} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                </>
              )}
              {r.shape === "point" && <circle cx={ax} cy={ay} r={1.2 * unit} className={cx(t.fill, "stroke-white")} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />}
              {/* a ring finds small places (a city, a tiny country) at a glance */}
              {r.shape !== "line" && r.label === null && <circle cx={ax} cy={ay} r={3 * unit} fill="none" className={t.stroke} strokeWidth={2} vectorEffect="non-scaling-stroke" />}
            </g>
          );
        })}
        {/* letters on top of every shape, so no region can hide another's letter */}
        {labelled.map((r) => {
          const t = TONE[toneFor(r)];
          const [ax, ay] = r.anchor;
          return (
            <g key={`badge-${r.label}`} data-badge={r.label!} onClick={() => pick(r.label)} className={cx(clickable && "cursor-pointer")}>
              <circle cx={ax} cy={ay} r={badge * 1.5} fill="transparent" />
              {r.shape !== "line" && <circle cx={ax} cy={ay} r={badge * 1.35} fill="none" className={t.stroke} strokeWidth={1.5} strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />}
              <circle cx={ax} cy={ay} r={badge} className={cx(t.badge, "stroke-white")} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
              <text x={ax} y={ay} textAnchor="middle" dominantBaseline="central" className="fill-white font-semibold" fontSize={badge * 1.15} pointerEvents="none">
                {r.label}
              </text>
            </g>
          );
        })}
      </svg>
    );
  }

  return (
    <figure className={cx("space-y-2", className)}>
      {body}
      <figcaption className="text-xs text-ink-faint">{MAP_NOTICE}</figcaption>
    </figure>
  );
}
