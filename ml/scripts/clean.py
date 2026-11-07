"""Clean a raw dataset into the canonical interaction table (data/processed/<name>.parquet).

Usage (from ml/):
    python scripts/clean.py --dataset assist2009 [--include-scaffolding]
    python scripts/clean.py --dataset ednet [--n-students 10000]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from mentorx_ml.data import assist2009, ednet

ML_DIR = Path(__file__).resolve().parents[1]


def _raw(name: str, filename: str) -> Path:
    path = ML_DIR / "data" / "raw" / name / filename
    if not path.exists():
        raise SystemExit(f"{path} not found. Run scripts/download.py --dataset {name} first.")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", choices=[assist2009.NAME, ednet.NAME], required=True)
    parser.add_argument("--include-scaffolding", action="store_true", help="assist2009 only")
    parser.add_argument("--n-students", type=int, default=10000, help="ednet only")
    args = parser.parse_args()

    notes: dict = {}
    if args.dataset == assist2009.NAME:
        cfg = assist2009.CleaningConfig(include_scaffolding=args.include_scaffolding)
        raw = assist2009.load_raw(_raw(args.dataset, assist2009.REMOTE.filename))
        df, report = assist2009.clean(raw, cfg)
        name = args.dataset + ("_with_scaffolding" if args.include_scaffolding else "")
        cfg_dict = asdict(cfg)
    else:
        cfg = ednet.SampleConfig(n_students=args.n_students)
        questions = ednet.load_questions(_raw(args.dataset, ednet.CONTENTS.filename))
        raw, total = ednet.sample_students(_raw(args.dataset, ednet.KT1.filename), cfg)
        df, report = ednet.clean(raw, questions, cfg)
        name = args.dataset
        cfg_dict = asdict(cfg)
        notes = {"students_in_full_dataset": total, "questions_in_contents": len(questions)}

    out_dir = ML_DIR / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.parquet"
    df.to_parquet(out_path, index=False)

    # The cleaning log contains only counts, so it's committed under reports/.
    report_dir = ML_DIR / "reports" / "eda" / name
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "cleaning.md").write_text(report.as_markdown() + "\n", encoding="utf-8")
    (report_dir / "cleaning_config.json").write_text(
        json.dumps({**cfg_dict, **notes}, indent=2, default=list) + "\n", encoding="utf-8"
    )

    print(report.as_markdown())
    if notes:
        print(notes)
    print(f"\nWrote {out_path} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
