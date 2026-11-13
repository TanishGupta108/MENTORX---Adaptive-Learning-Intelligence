"""Build the Geography map assets from the open slepemapy SVG maps (MIT licence).

Source SVGs: https://github.com/adaptive-learning/geography (geography/static/map/<map>.svg,
"Copyright (c) 2013 Vit Stanislav", MIT). They are not committed; download the six shipped maps
into one folder and pass it with --svg-dir.

Outputs (both committed; neither contains answers in a form the client can use):
- frontend/public/maps/<map>.json         {"viewBox", "land": [path d, ...], "notice"}
  Land outlines only (unlabelled background + countries/states + islands), WITHOUT place codes,
  names or ids, so the client can draw the map but cannot tell which outline is which place.
- backend/app/tutor/seeddata/geography/geometry_<map>.json   {code: {d, anchor, bbox, shape}}
  Server-only geometry of every askable place, used by the seed to build item media.

Scope and safety rules (spec A2):
- Only the six whitelisted maps are built. World, Asia, India and China maps are never shipped.
- A map is rejected if any element carries a South Asian code (data-code or data-state-code).
- Disputed places (Kosovo, Western Sahara, Somaliland, Falklands, and the cities in them) are kept
  as plain land in the base map but get no geometry entry, so they can never be asked or offered.

Coordinates are rounded to 1 decimal in the map's own viewBox (the SVGs have no transforms;
the script asserts that). Paths use only absolute M/L/Z commands (asserted too).

    python ml/scripts/build_geography_maps.py --svg-dir <folder with the six SVGs>
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONT_DIR = ROOT / "frontend" / "public" / "maps"
SEED_DIR = ROOT / "backend" / "app" / "tutor" / "seeddata" / "geography"
NS = "{http://www.w3.org/2000/svg}"

MAPS = ("europe", "africa", "samerica", "namerica", "oceania", "us")
SOUTH_ASIA = {"in", "pk", "cn", "np", "bt", "bd", "mm", "lk", "af"}
DISPUTED = {"xk", "eh", "xs", "fk", "ps", "tw"}
# Cities inside disputed territories. Laayoune is tagged "ma" in the source SVG but lies in
# Western Sahara, so it is listed by name.
DISPUTED_CITIES = {"pristina", "bir_lehlou", "laayoune", "hargeysa"}
LAND_GROUPS = ("bg", "state", "island")  # drawn as plain land in the base map
SHAPES = {"state": "area", "island": "area", "mountains": "area", "river": "line", "city": "point"}
NOTICE = (
    "Map outlines: adaptive-learning/geography (https://github.com/adaptive-learning/geography), "
    "MIT licence, (c) 2013 Vit Stanislav. Simplified for practice; they do not show official "
    "international boundaries."
)

_TOKEN = re.compile(r"[MLZmlz]|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def parse_path(d: str) -> list[tuple[list[tuple[float, float]], bool]]:
    """Subpaths of an absolute M/L/Z path as (points, closed)."""
    toks = _TOKEN.findall(d)
    leftovers = _TOKEN.sub("", d).replace(",", "").strip()
    assert not leftovers, f"unsupported path syntax: {leftovers[:40]!r}"
    out: list[tuple[list[tuple[float, float]], bool]] = []
    cur: list[tuple[float, float]] = []
    cmd, i = None, 0
    while i < len(toks):
        t = toks[i]
        if t in "MLZmlz":
            assert t in "MLZ", f"relative path command {t} not supported"
            if t == "Z":
                if cur:
                    out.append((cur, True))
                cur = []
            elif t == "M" and cur:
                out.append((cur, False))
                cur = []
            cmd = t
            i += 1
            continue
        assert cmd in ("M", "L"), "number without a command"
        cur.append((float(t), float(toks[i + 1])))
        i += 2
    if cur:
        out.append((cur, False))
    return out


def _r(v: float) -> float:
    return round(v + 0.0, 1) + 0.0  # + 0.0 turns -0.0 into 0.0


def fmt(subpaths: list[tuple[list[tuple[float, float]], bool]]) -> str:
    """Rounded path string; consecutive duplicate points dropped, degenerate rings removed."""
    parts = []
    for pts, closed in subpaths:
        rounded: list[tuple[float, float]] = []
        for x, y in pts:
            p = (_r(x), _r(y))
            if not rounded or rounded[-1] != p:
                rounded.append(p)
        if closed and len(rounded) > 1 and rounded[0] == rounded[-1]:
            rounded.pop()
        if len(rounded) < (3 if closed else 2):
            continue
        s = "M" + "L".join(f"{x:g},{y:g}" for x, y in rounded)
        parts.append(s + ("Z" if closed else ""))
    return "".join(parts)


def ring_area(pts: list[tuple[float, float]]) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True):
        a += x1 * y2 - x2 * y1
    return a / 2


def _seg_dist2(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx or dy:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        ax, ay = ax + t * dx, ay + t * dy
    return (px - ax) ** 2 + (py - ay) ** 2


def _signed_dist(x: float, y: float, ring: list[tuple[float, float]]) -> float:
    inside, best = False, math.inf
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1], strict=True):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
        best = min(best, _seg_dist2(x, y, ax, ay, bx, by))
    return (1 if inside else -1) * math.sqrt(best)


def polylabel(ring: list[tuple[float, float]], precision: float = 0.5) -> tuple[float, float]:
    """Point inside the polygon farthest from its edges (Mapbox polylabel algorithm)."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
    size = min(maxx - minx, maxy - miny)
    if size == 0:
        return (minx, miny)
    h = size / 2
    heap: list[tuple[float, float, float, float, float]] = []

    def push(x: float, y: float, half: float) -> None:
        d = _signed_dist(x, y, ring)
        heapq.heappush(heap, (-(d + half * math.sqrt(2)), d, x, y, half))

    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            push(x + h, y + h, h)
            y += size
        x += size
    a = ring_area(ring)
    cx = sum(
        (x1 + x2) * (x1 * y2 - x2 * y1)
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True)
    )
    cy = sum(
        (y1 + y2) * (x1 * y2 - x2 * y1)
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True)
    )
    best = ((minx + maxx) / 2, (miny + maxy) / 2)
    best_d = _signed_dist(*best, ring)
    if a:
        c = (cx / (6 * a), cy / (6 * a))
        cd = _signed_dist(*c, ring)
        if cd > best_d:
            best, best_d = c, cd
    while heap:
        neg_max, d, x, y, half = heapq.heappop(heap)
        if d > best_d:
            best, best_d = (x, y), d
        if -neg_max - best_d <= precision:
            continue
        half /= 2
        for dx in (-half, half):
            for dy in (-half, half):
                push(x + dx, y + dy, half)
    return best


def line_midpoint(subpaths) -> tuple[float, float]:
    """Point halfway along the longest subpath of a line."""

    def length(pts):
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:], strict=False))

    pts = max((p for p, _ in subpaths), key=length)
    half, run = length(pts) / 2, 0.0
    for a, b in zip(pts, pts[1:], strict=False):
        seg = math.dist(a, b)
        if run + seg >= half and seg:
            t = (half - run) / seg
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        run += seg
    return pts[len(pts) // 2]


def clip_ring(ring: list[tuple[float, float]], w: float, h: float) -> list[tuple[float, float]]:
    """The part of a polygon inside the viewBox (Sutherland-Hodgman against its 4 edges)."""
    edges = (
        (lambda p: p[0] >= 0, lambda a, b: _cross_x(a, b, 0.0)),
        (lambda p: p[0] <= w, lambda a, b: _cross_x(a, b, w)),
        (lambda p: p[1] >= 0, lambda a, b: _cross_y(a, b, 0.0)),
        (lambda p: p[1] <= h, lambda a, b: _cross_y(a, b, h)),
    )
    out = list(ring)
    for inside, cross in edges:
        src, out = out, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        if not out:
            break
    return out


def _cross_x(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _cross_y(a, b, y):
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def visible_runs(pts, w: float, h: float) -> list[list[tuple[float, float]]]:
    """Runs of consecutive line points inside the viewBox."""
    runs: list[list[tuple[float, float]]] = [[]]
    for p in pts:
        if 0 <= p[0] <= w and 0 <= p[1] <= h:
            runs[-1].append(p)
        elif runs[-1]:
            runs.append([])
    return [r for r in runs if len(r) >= 2]


def bbox(points) -> list[float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [_r(min(xs)), _r(min(ys)), _r(max(xs)), _r(max(ys))]


def build_map(svg_path: Path) -> tuple[dict, dict, dict]:
    root = ET.parse(svg_path).getroot()
    assert "transform" not in ET.tostring(root, encoding="unicode"), "transforms not supported"
    view_box = root.get("viewBox")
    # the seed measures the 6 % letter spacing in a 1000-unit-wide viewBox
    assert view_box.split()[:3] == ["0", "0", "1000"], f"{svg_path.name}: viewBox {view_box}"
    vw, vh = (float(v) for v in view_box.split()[2:])
    codes = set()
    for el in root.iter():
        for attr in ("data-code", "data-state-code"):
            if el.get(attr):
                codes.add(el.get(attr).lower())
    bad = sorted(codes & SOUTH_ASIA)
    assert not bad, f"{svg_path.name}: South Asian codes present {bad}: map must not ship"

    land: list[str] = []
    geometry: dict[str, dict] = {}
    skipped: list[str] = []
    for g in root.iter(NS + "g"):
        gid = g.get("id")
        for el in g:
            code = (el.get("data-code") or "").lower()
            state = (el.get("data-state-code") or "").lower()
            if el.tag == NS + "path":
                sub = parse_path(el.get("d", ""))
                if gid in LAND_GROUPS:
                    d = fmt(sub)
                    if d:
                        land.append(d)
            if gid not in SHAPES or not code:
                continue
            if code in DISPUTED or state in DISPUTED or code in DISPUTED_CITIES:
                skipped.append(code)
                continue
            shape = SHAPES[gid]
            if shape == "point":
                cx, cy = float(el.get("cx")), float(el.get("cy"))
                geometry[code] = {
                    "d": "",
                    "anchor": [_r(cx), _r(cy)],
                    "bbox": [_r(cx), _r(cy), _r(cx), _r(cy)],
                    "shape": "point",
                }
                continue
            # anchors and boxes use only the part of the place inside the map's viewBox
            if shape == "line":
                runs = [r for s, _ in sub for r in visible_runs(s, vw, vh)]
                assert runs, f"{svg_path.name}: {code} is not visible"
                anchor = line_midpoint([(r, False) for r in runs])
                pts = [p for r in runs for p in r]
            else:
                rings = [c for c in (clip_ring(s, vw, vh) for s, _ in sub) if len(c) >= 3]
                assert rings, f"{svg_path.name}: {code} is not visible"
                ring = max(rings, key=lambda r: abs(ring_area(r)))
                anchor = polylabel(ring)
                pts = [p for r in rings for p in r]
            d = fmt(sub)
            assert d, f"{svg_path.name}: {code} has no drawable geometry"
            geometry[code] = {
                "d": d,
                "anchor": [_r(anchor[0]), _r(anchor[1])],
                "bbox": bbox(pts),
                "shape": shape,
            }
    base = {"viewBox": view_box, "land": land, "notice": NOTICE}
    report = {
        "view_box": view_box,
        "land_paths": len(land),
        "places": len(geometry),
        "skipped": skipped,
    }
    return base, geometry, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--svg-dir", required=True, type=Path)
    args = ap.parse_args()
    FRONT_DIR.mkdir(parents=True, exist_ok=True)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for m in MAPS:
        base, geometry, report = build_map(args.svg_dir / f"{m}.svg")
        (FRONT_DIR / f"{m}.json").write_text(
            json.dumps(base, separators=(",", ":")), encoding="utf-8", newline="\n"
        )
        (SEED_DIR / f"geometry_{m}.json").write_text(
            json.dumps(geometry, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
        size = (FRONT_DIR / f"{m}.json").stat().st_size
        print(f"{m:9s} {report} base {size:,} bytes")


if __name__ == "__main__":
    main()
