"""Load the Geography subject (map skills, Slepemapy.cz) into the database.

    python scripts/seed_geography.py --data-dir "C:/Users/me/Downloads/slepemapy-2015-05-21"

The folder must contain place.csv from the Slepemapy.cz 2015-05-21 data set
(http://www.fi.muni.cz/adaptivelearning/data/slepemapy/2015-05-21.zip, Open Database License 1.0).
GEO_DATA_DIR can be used instead of --data-dir. Everything else (skills, question statistics,
map geometry, notes) ships with the code. Safe to run again: it updates in place, keeps admin
edits (skill descriptions, question availability) and never touches Mathematics.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.db.session import get_sessionmaker  # noqa: E402
from app.tutor.seed_geo import seed_geography  # noqa: E402

ARTIFACTS = BACKEND / "model_artifacts" / "geography"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", type=Path, default=os.environ.get("GEO_DATA_DIR"))
    args = ap.parse_args()
    if not args.data_dir or not (Path(args.data_dir) / "place.csv").exists():
        sys.exit("Pass --data-dir (or set GEO_DATA_DIR) to the Slepemapy folder with place.csv")
    if not (ARTIFACTS / "kt_meta.json").exists():
        sys.exit(f"Missing {ARTIFACTS / 'kt_meta.json'}: the Geography model artifacts")
    with get_sessionmaker()() as db:
        summary = seed_geography(db, Path(args.data_dir), ARTIFACTS)
    for k, v in summary.items():
        print(f"{k:>16}: {v}")


if __name__ == "__main__":
    main()
