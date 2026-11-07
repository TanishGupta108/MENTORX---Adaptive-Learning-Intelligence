"""The canonical interaction table every dataset is converted into.

Public datasets (ASSISTments, EdNet) and the MENTORX pilot export are all cleaned
into this one shape, so features, models and evaluation code work on any of them.
"""

from __future__ import annotations

import pandas as pd

# column -> pandas dtype
CANONICAL_COLUMNS: dict[str, str] = {
    "student_id": "string",
    "item_id": "string",
    "concept_id": "string",
    "correct": "int8",  # 1 = correct on first attempt
    "seq": "int64",  # 0-based position of this interaction in the student's history
    "timestamp": "datetime64[ns, UTC]",  # NaT when the source has no clock time
    "response_ms": "float64",  # NaN when unknown
    "attempt_count": "Int64",  # attempts on this item in this interaction (nullable)
    "hint_count": "Int64",
    "source": "string",
}


class SchemaError(ValueError):
    pass


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Check a frame matches the canonical schema and ordering rules. Returns it unchanged."""
    missing = set(CANONICAL_COLUMNS) - set(df.columns)
    if missing:
        raise SchemaError(f"missing columns: {sorted(missing)}")
    if df[["student_id", "item_id", "concept_id", "correct", "seq"]].isna().any().any():
        raise SchemaError("student_id, item_id, concept_id, correct and seq must not be null")
    if not df["correct"].isin([0, 1]).all():
        raise SchemaError("correct must be 0 or 1")
    if (df["response_ms"].dropna() <= 0).any():
        raise SchemaError("response_ms must be positive when present")

    # seq must be exactly 0..n-1 within each student, and rows sorted by (student, seq),
    # because every feature is computed from strictly earlier rows.
    expected = df.groupby("student_id", sort=False).cumcount()
    if not (df["seq"].to_numpy() == expected.to_numpy()).all():
        raise SchemaError("rows must be sorted by student then seq, with seq = 0..n-1")
    return df


def to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """Select canonical columns in order and cast dtypes."""
    out = df[list(CANONICAL_COLUMNS)].copy()
    for col, dtype in CANONICAL_COLUMNS.items():
        if dtype.startswith("datetime"):
            out[col] = pd.to_datetime(out[col], utc=True)
        else:
            out[col] = out[col].astype(dtype)
    return out.reset_index(drop=True)
