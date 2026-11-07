"""EdNet-KT1 (Santa TOEIC app): a fixed random sample of students.

Source: https://github.com/riiid/ednet. Licence: CC BY-NC 4.0 (non-commercial research).
KT1 is one CSV per student inside a 1.2 GB zip (784k students); we read a reproducible
random sample straight from the zip without extracting it.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from mentorx_ml.data.assist2009 import CleaningReport
from mentorx_ml.data.download import RemoteFile
from mentorx_ml.data.schema import to_canonical, validate

NAME = "ednet"

KT1 = RemoteFile(
    url="https://drive.usercontent.google.com/download?id=1AmGcOs5U31wIIqvthn9ARqJMrMTFTcaw&export=download&confirm=t",
    filename="EdNet-KT1.zip",
    sha256="0d13933f90201c5101c7fe8659e44474fa049e3fb93181a8ba6fb3e63267b535",
)
CONTENTS = RemoteFile(
    url="https://drive.usercontent.google.com/download?id=117aYJAWG3GU48suS66NPaB82HwFj6xWS&export=download&confirm=t",
    filename="EdNet-Contents.zip",
    sha256="aa910a0436d9dbac0ba232f55e27b37ad8d39da285fcf15f1c1eb5d064be98e7",
)


@dataclass
class SampleConfig:
    n_students: int = 10000
    seed: int = 42
    # The concept of a question. "tags" = its full tag set (e.g. "179;53;183"), treated as one
    # concept, which mirrors the collapsed multi-skill tags used for ASSISTments.
    concept: str = "tags"
    extra: dict = field(default_factory=dict)


def load_questions(contents_zip: Path) -> pd.DataFrame:
    with zipfile.ZipFile(contents_zip) as z:
        # The zip also holds macOS metadata files such as __MACOSX/contents/._questions.csv.
        name = next(n for n in z.namelist() if n.endswith("questions.csv") and "__MACOSX" not in n)
        with z.open(name) as f:
            q = pd.read_csv(f, dtype=str)
    return q[["question_id", "bundle_id", "correct_answer", "part", "tags"]]


def sample_students(kt1_zip: Path, cfg: SampleConfig) -> tuple[pd.DataFrame, int]:
    """Read cfg.n_students randomly chosen student files. Returns (rows, students in zip)."""
    with zipfile.ZipFile(kt1_zip) as z:
        members = sorted(n for n in z.namelist() if n.endswith(".csv") and "__MACOSX" not in n)
        rng = np.random.default_rng(cfg.seed)
        chosen = rng.choice(len(members), size=min(cfg.n_students, len(members)), replace=False)
        frames = []
        for i in sorted(chosen):
            name = members[i]
            with z.open(name) as f:
                df = pd.read_csv(
                    io.BytesIO(f.read()), dtype={"question_id": str, "user_answer": str}
                )
            df["user_id"] = Path(name).stem
            df["file_row"] = np.arange(len(df))
            frames.append(df)
    return pd.concat(frames, ignore_index=True), len(members)


def clean(
    raw: pd.DataFrame, questions: pd.DataFrame, cfg: SampleConfig | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    cfg = cfg or SampleConfig()
    report = CleaningReport()
    df = raw.copy()
    report.record("sampled students (raw rows)", df, "user_id")

    df = df.merge(questions, on="question_id", how="inner")
    report.record("keep questions present in questions.csv", df, "user_id")

    df = df[df["user_answer"].notna() & df["correct_answer"].notna()]
    report.record("drop rows with no submitted answer", df, "user_id")

    # Within a student, order by timestamp; questions of one bundle share a timestamp,
    # so the original file order breaks ties.
    df = df.sort_values(["user_id", "timestamp", "file_row"], kind="stable")

    concept = df["tags"] if cfg.concept == "tags" else df["part"]
    out = pd.DataFrame(
        {
            "student_id": df["user_id"].to_numpy(),
            "item_id": df["question_id"].to_numpy(),
            "concept_id": concept.astype(str).to_numpy(),
            "correct": (df["user_answer"] == df["correct_answer"]).astype(int).to_numpy(),
            "timestamp": pd.to_datetime(df["timestamp"].to_numpy(), unit="ms", utc=True),
            "response_ms": df["elapsed_time"]
            .where(df["elapsed_time"] > 0, np.nan)
            .to_numpy(dtype="float64"),
            "attempt_count": pd.NA,
            "hint_count": pd.NA,
            "source": NAME,
        }
    )
    out["seq"] = out.groupby("student_id", sort=False).cumcount()
    out = to_canonical(out)
    validate(out)
    return out, report
