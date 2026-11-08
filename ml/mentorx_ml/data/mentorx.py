"""The MENTORX pilot export (Phase B training data, M11).

Input: the admin export `mentorx-attempts.csv` (Study page -> "Answers (for retraining)"),
copied to data/raw/mentorx/. It holds only consenting students, already pseudonymised.
Never commit it: data/ is git-ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from mentorx_ml.data.assist2009 import CleaningReport
from mentorx_ml.data.schema import to_canonical, validate

NAME = "mentorx"
FILENAME = "mentorx-attempts.csv"

EXPORT_COLUMNS = [
    "student",
    "attempt_id",
    "timestamp",
    "session_type",
    "question",
    "concept",
    "correct",
    "response_ms",
    "valid",
]


@dataclass
class CleaningConfig:
    # Answers under the 3 s minimum are likely rapid guesses (FR-ENG-02) and add noise.
    drop_invalid: bool = True
    # Pre/post-test answers are real responses too; keep them unless studying practice only.
    include_tests: bool = True
    # Students with fewer answers than this carry almost no sequence information.
    min_answers: int = 5


def load_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"student": str, "question": str, "concept": str})
    missing = set(EXPORT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing columns {sorted(missing)}; is it the attempts export?"
        )
    return df


def clean(
    raw: pd.DataFrame, cfg: CleaningConfig | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    cfg = cfg or CleaningConfig()
    report = CleaningReport()
    df = raw.copy()
    report.record("exported answers (consenting students)", df, "student")

    if cfg.drop_invalid:
        df = df[df["valid"] == 1]
        report.record("drop answers under the 3 s minimum", df, "student")
    if not cfg.include_tests:
        df = df[~df["session_type"].isin(["pretest", "posttest"])]
        report.record("drop pre/post-test answers", df, "student")

    counts = df.groupby("student")["attempt_id"].transform("size")
    df = df[counts >= cfg.min_answers]
    report.record(f"drop students with < {cfg.min_answers} answers", df, "student")

    # attempt_id increases with insertion order, so it breaks timestamp ties reliably.
    df = df.assign(_ts=pd.to_datetime(df["timestamp"], utc=True)).sort_values(
        ["student", "_ts", "attempt_id"], kind="stable"
    )
    out = pd.DataFrame(
        {
            "student_id": df["student"].to_numpy(),
            "item_id": df["question"].to_numpy(),
            "concept_id": df["concept"].to_numpy(),
            "correct": df["correct"].astype(int).to_numpy(),
            "timestamp": df["_ts"].to_numpy(),
            "response_ms": pd.to_numeric(df["response_ms"], errors="coerce")
            .where(lambda s: s > 0, np.nan)
            .to_numpy(dtype="float64"),
            "attempt_count": 1,  # one submission per served question
            "hint_count": 0,  # MENTORX has no hints
            "source": NAME,
        }
    )
    out["seq"] = out.groupby("student_id", sort=False).cumcount()
    out = to_canonical(out)
    validate(out)
    return out, report
