"""ASSISTments 2009-2010 Skill Builder (corrected, collapsed version).

Source page: https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010
Terms: see docs/datasets.md. The data is free to use but must not be redistributed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from mentorx_ml.data.download import RemoteFile
from mentorx_ml.data.schema import to_canonical, validate

NAME = "assist2009"

REMOTE = RemoteFile(
    url=(
        "https://drive.usercontent.google.com/download"
        "?id=1NNXHFRxcArrU0ZJSb9BIL56vmUt5FhlE&export=download&confirm=t"
    ),
    filename="skill_builder_data_corrected_collapsed.csv",
    sha256="162ef8d2d28bcbfea6591a282994062bd8d5eaa00636544292a0d268dca6e5da",
)

RAW_COLUMNS = [
    "order_id",
    "user_id",
    "problem_id",
    "skill_id",
    "original",
    "correct",
    "attempt_count",
    "ms_first_response",
    "hint_count",
    "tutor_mode",
    "answer_type",
]


@dataclass
class CleaningConfig:
    # MENTORX has no scaffolding sub-questions, so by default only main problems are kept.
    # Set True to match papers that use every row.
    include_scaffolding: bool = False
    # "open_response" answers are always marked correct/incorrect by rule, not by
    # the student's knowledge, so their labels carry no signal.
    drop_answer_types: tuple[str, ...] = ("open_response",)
    keep_tutor_modes: tuple[str, ...] = ("tutor",)


@dataclass
class CleaningReport:
    steps: list[tuple[str, int, int]] = field(default_factory=list)  # (step, rows, students)

    def record(self, step: str, df: pd.DataFrame, student_col: str) -> None:
        self.steps.append((step, len(df), int(df[student_col].nunique())))

    def as_markdown(self) -> str:
        lines = ["| Step | Rows | Students | Rows removed |", "|---|---:|---:|---:|"]
        prev = None
        for step, rows, students in self.steps:
            removed = "" if prev is None else f"{prev - rows:,}"
            lines.append(f"| {step} | {rows:,} | {students:,} | {removed} |")
            prev = rows
        return "\n".join(lines)


def load_raw(path: Path) -> pd.DataFrame:
    # The file contains a few non-UTF-8 bytes in free-text columns; latin-1 reads every byte.
    return pd.read_csv(path, usecols=RAW_COLUMNS, encoding="latin-1", low_memory=False)


def clean(
    raw: pd.DataFrame, config: CleaningConfig | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    """Turn raw rows into the canonical interaction table. Pure function: no I/O."""
    cfg = config or CleaningConfig()
    report = CleaningReport()
    df = raw.copy()
    report.record("raw file", df, "user_id")

    df = df[df["skill_id"].notna()]
    report.record("drop rows with no skill tag", df, "user_id")

    df = df[~df["answer_type"].isin(cfg.drop_answer_types)]
    report.record(f"drop answer types {list(cfg.drop_answer_types)}", df, "user_id")

    df = df[df["tutor_mode"].isin(cfg.keep_tutor_modes)]
    report.record(f"keep tutor modes {list(cfg.keep_tutor_modes)}", df, "user_id")

    if not cfg.include_scaffolding:
        df = df[df["original"] == 1]
        report.record("keep main problems only (drop scaffolding)", df, "user_id")

    # order_id is the only clock: it's assigned chronologically by the tutor.
    df = df.sort_values(["user_id", "order_id"], kind="stable")

    out = pd.DataFrame(
        {
            "student_id": df["user_id"].astype(str).to_numpy(),
            "item_id": df["problem_id"].astype(str).to_numpy(),
            # Collapsed multi-skill tags such as "1_13" are treated as one concept.
            "concept_id": df["skill_id"].astype(str).to_numpy(),
            "correct": df["correct"].to_numpy(),
            "timestamp": pd.NaT,  # the dataset has no clock time
            "response_ms": df["ms_first_response"]
            .where(df["ms_first_response"] > 0, np.nan)
            .to_numpy(dtype="float64"),
            "attempt_count": df["attempt_count"].to_numpy(),
            "hint_count": df["hint_count"].to_numpy(),
            "source": NAME,
        }
    )
    out["seq"] = out.groupby("student_id", sort=False).cumcount()
    out = to_canonical(out)
    validate(out)
    return out, report
