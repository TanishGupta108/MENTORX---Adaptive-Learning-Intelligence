"""Load a subject's question bank into the database.

Usage (from backend/, after `alembic upgrade head`):
    python scripts/seed.py                       # machine_learning, drafts per environment
    python scripts/seed.py --reviewed-only       # force production behaviour
    python scripts/seed.py --include-drafts      # force development behaviour

In production (ENVIRONMENT=production) only questions marked `review_status: reviewed`
are loaded unless --include-drafts is given.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.content.question_bank import QUESTION_BANK_DIR, load_question_bank  # noqa: E402
from app.content.seed import seed  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("subject", nargs="?", default="machine_learning")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--include-drafts", action="store_true")
    group.add_argument("--reviewed-only", action="store_true")
    args = parser.parse_args()

    include = get_settings().include_draft_questions
    if args.include_drafts:
        include = True
    if args.reviewed_only:
        include = False

    bank = load_question_bank(QUESTION_BANK_DIR / args.subject)  # validates; raises on error
    with get_sessionmaker()() as db:
        report = seed(db, bank, include_drafts=include)
    print(report.summary())
    for w in report.warnings:
        print(f"WARNING: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
