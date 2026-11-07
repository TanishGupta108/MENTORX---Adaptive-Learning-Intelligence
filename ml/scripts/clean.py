"""Clean a raw dataset into the canonical interaction table (data/processed/<name>.parquet).

Usage (from ml/):  python scripts/clean.py --dataset assist2009 [--include-scaffolding]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mentorx_ml.data import assist2009

ML_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=[assist2009.NAME], required=True)
    parser.add_argument("--include-scaffolding", action="store_true")
    args = parser.parse_args()

    raw_path = ML_DIR / "data" / "raw" / args.dataset / assist2009.REMOTE.filename
    if not raw_path.exists():
        raise SystemExit(f"{raw_path} not found. Run scripts/download.py first.")

    cfg = assist2009.CleaningConfig(include_scaffolding=args.include_scaffolding)
    df, report = assist2009.clean(assist2009.load_raw(raw_path), cfg)

    suffix = "_with_scaffolding" if args.include_scaffolding else ""
    out_dir = ML_DIR / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.dataset}{suffix}.parquet"
    df.to_parquet(out_path, index=False)

    # The cleaning log contains only counts, so it's committed under reports/.
    report_dir = ML_DIR / "reports" / "eda" / f"{args.dataset}{suffix}"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "cleaning.md").write_text(report.as_markdown() + "\n", encoding="utf-8")
    (report_dir / "cleaning_config.json").write_text(
        json.dumps(cfg.__dict__, indent=2, default=list) + "\n", encoding="utf-8"
    )

    print(report.as_markdown())
    print(f"\nWrote {out_path} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
