"""Recompute every student's skill states with the current diagnosis rules (run once after a
rule change, e.g. the 2026-11-14 "answers decide after 5" fix).

    python scripts/refresh_states.py --dry-run    # count what would change, change nothing
    python scripts/refresh_states.py              # apply (safe to run again)

Uses DATABASE_URL (or backend/.env) like the app. Prints counts only, never who.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_sessionmaker  # noqa: E402
from app.tutor.state import refresh_everyone  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="count only, change nothing")
    args = ap.parse_args()
    with get_sessionmaker()() as db:
        out = refresh_everyone(db, dry_run=args.dry_run)
    if args.dry_run:
        print("DRY RUN: nothing was changed")
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
