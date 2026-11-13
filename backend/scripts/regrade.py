"""Re-check stored typed answers with the current answer checker (wrong -> right only).

    python scripts/regrade.py --dry-run     # show what would change, change nothing
    python scripts/regrade.py               # apply (safe to run again: it is idempotent)

Uses DATABASE_URL (or backend/.env) like the app. See app/tutor/regrade.py for the rules.
Prints counts and one line per changed answer (question id, answer id; never who answered).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_sessionmaker  # noqa: E402
from app.tutor.regrade import regrade  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    ap.add_argument("--quiet", action="store_true", help="counts only, no per-answer lines")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    with get_sessionmaker()() as db:
        rep = regrade(db, dry_run=args.dry_run)
    print("DRY RUN: nothing was changed" if args.dry_run else "Regrade applied")
    if not args.quiet:
        for item_id, inter_id in rep.changes:
            print(f"  question {item_id}, answer {inter_id}: wrong -> correct")
    for line in rep.lines():
        print(line)


if __name__ == "__main__":
    main()
