"""Student-level train/validation/test splitting.

Every attempt by a given student goes into exactly one split, so the model is
always evaluated on students it has never seen. A row-level random split would
leak each student's ability into the test set and inflate the metrics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StudentSplit:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


def split_by_student(
    df: pd.DataFrame,
    student_col: str = "student_id",
    val_frac: float = 0.15,
    test_frac: float = 0.15,
    seed: int = 42,
) -> StudentSplit:
    if not 0 < val_frac < 1 or not 0 < test_frac < 1 or val_frac + test_frac >= 1:
        raise ValueError("val_frac and test_frac must be in (0, 1) and sum to less than 1")

    students = np.sort(df[student_col].unique())
    if len(students) < 3:
        raise ValueError("need at least 3 students to make three splits")

    rng = np.random.default_rng(seed)
    rng.shuffle(students)

    n = len(students)
    n_test = max(1, round(n * test_frac))
    n_val = max(1, round(n * val_frac))
    test_ids = set(students[:n_test])
    val_ids = set(students[n_test : n_test + n_val])

    is_test = df[student_col].isin(test_ids)
    is_val = df[student_col].isin(val_ids)
    return StudentSplit(
        train=df[~is_test & ~is_val],
        val=df[is_val],
        test=df[is_test],
    )
