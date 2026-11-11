"""Load the Mathematics subject (FoundationalASSIST) into the database.

    python scripts/seed_math.py --data-dir "C:/Users/me/Downloads"

The folder must contain Problems.csv and Skills.csv from FoundationalASSIST (download it from
https://huggingface.co/datasets/ASSISTments/FoundationalASSIST after accepting its terms).
MATH_DATA_DIR can be used instead of --data-dir. Safe to run again: it updates in place and
keeps admin edits (skill descriptions, question availability, added resources and links).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.tutor.seed import seed_math  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, default=os.environ.get("MATH_DATA_DIR"))
    ap.add_argument("--keep-other-subjects", action="store_true", help="don't hide other subjects")
    args = ap.parse_args()
    if not args.data_dir or not (Path(args.data_dir) / "Problems.csv").exists():
        sys.exit(
            "Pass --data-dir (or set MATH_DATA_DIR) to the folder with Problems.csv and Skills.csv"
        )
    artifacts = Path(__file__).resolve().parents[1] / get_settings().kt_artifacts_dir
    with get_sessionmaker()() as db:
        summary = seed_math(db, Path(args.data_dir), artifacts, not args.keep_other_subjects)
    for k, v in summary.items():
        print(f"{k:>18}: {v}")


if __name__ == "__main__":
    main()
