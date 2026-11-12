"""Check which FoundationalASSIST question images still load, once, before seeding.

    python scripts/check_images.py --data-dir "C:/Users/me/Downloads"

Reads Problems.csv, collects every real image address (WIRIS formula images are skipped:
the seed turns them into MathML), requests each one and writes `image_check.json` next to
the CSVs. scripts/seed_math.py reads that file: a question with an image is served only if
every image in it answered 200 with an image content type. Run it again any time; the
seed simply uses the latest file. Without the file, image questions stay unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tutor.html import scan_images  # noqa: E402

COLUMNS = ("Problem Body", "Multiple Choice Options", "Fill-in Options")
HEADERS = {"User-Agent": "MENTORX-image-check/1.0 (educational project)"}


def collect(problems: pd.DataFrame) -> list[str]:
    urls: set[str] = set()
    for col in COLUMNS:
        for raw in problems[col].dropna().astype(str):
            found, _ = scan_images(raw)
            urls.update(found)
    return sorted(urls)


def probe(client: httpx.Client, url: str) -> tuple[str, bool, str]:
    try:
        with client.stream("GET", url) as r:
            ctype = r.headers.get("content-type", "")
            ok = r.status_code == 200 and ctype.startswith("image/")
            return url, ok, f"{r.status_code} {ctype}".strip()
    except httpx.HTTPError as exc:
        return url, False, type(exc).__name__


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, default=os.environ.get("MATH_DATA_DIR"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=20)
    args = ap.parse_args()
    if not args.data_dir or not (Path(args.data_dir) / "Problems.csv").exists():
        sys.exit("Pass --data-dir (or set MATH_DATA_DIR) to the folder with Problems.csv")
    problems = pd.read_csv(Path(args.data_dir) / "Problems.csv")
    urls = collect(problems)
    print(f"checking {len(urls)} image addresses ...")
    results: dict[str, dict] = {}
    with (
        httpx.Client(timeout=args.timeout, follow_redirects=True, headers=HEADERS) as client,
        ThreadPoolExecutor(args.workers) as pool,
    ):
        for i, (url, ok, detail) in enumerate(pool.map(lambda u: probe(client, u), urls), 1):
            results[url] = {"ok": ok, "detail": detail}
            if i % 100 == 0:
                print(f"  {i}/{len(urls)}")
    out = Path(args.data_dir) / "image_check.json"
    out.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "results": results}, indent=1)
    )
    good = sum(1 for r in results.values() if r["ok"])
    print(f"{good} of {len(urls)} images load. Written to {out}")


if __name__ == "__main__":
    main()
