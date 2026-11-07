"""ASSISTments 2009 cleaning rules, tested on a tiny synthetic raw frame (no download)."""

import numpy as np
import pandas as pd
import pytest

from mentorx_ml.data import assist2009
from mentorx_ml.data.schema import SchemaError, validate


def _raw(rows):
    cols = assist2009.RAW_COLUMNS
    defaults = {
        "original": 1,
        "attempt_count": 1,
        "ms_first_response": 5000,
        "hint_count": 0,
        "tutor_mode": "tutor",
        "answer_type": "algebra",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])[cols]


ROWS = [
    # student 7: given out of order on purpose (order_id decides the sequence)
    {"order_id": 30, "user_id": 7, "problem_id": 3, "skill_id": "10", "correct": 1},
    {"order_id": 10, "user_id": 7, "problem_id": 1, "skill_id": "10", "correct": 0},
    {
        "order_id": 20,
        "user_id": 7,
        "problem_id": 2,
        "skill_id": "1_13",
        "correct": 1,
        "ms_first_response": 0,
    },
    # removed: no skill tag
    {"order_id": 40, "user_id": 7, "problem_id": 4, "skill_id": np.nan, "correct": 1},
    # removed: open response
    {
        "order_id": 50,
        "user_id": 7,
        "problem_id": 5,
        "skill_id": "10",
        "correct": 0,
        "answer_type": "open_response",
    },
    # removed: test mode
    {
        "order_id": 60,
        "user_id": 8,
        "problem_id": 6,
        "skill_id": "10",
        "correct": 1,
        "tutor_mode": "test",
    },
    # removed by default: scaffolding
    {"order_id": 70, "user_id": 8, "problem_id": 7, "skill_id": "10", "correct": 0, "original": 0},
    {"order_id": 80, "user_id": 8, "problem_id": 8, "skill_id": "11", "correct": 1},
]


def test_clean_applies_every_rule_and_orders_by_order_id():
    df, report = assist2009.clean(_raw(ROWS))
    assert list(df["item_id"]) == ["1", "2", "3", "8"]
    assert list(df["student_id"]) == ["7", "7", "7", "8"]
    assert list(df["seq"]) == [0, 1, 2, 0]
    assert list(df["correct"]) == [0, 1, 1, 1]
    assert [rows for _, rows, _ in report.steps] == [8, 7, 6, 5, 4]


def test_multi_skill_tag_is_kept_as_one_concept():
    df, _ = assist2009.clean(_raw(ROWS))
    assert "1_13" in set(df["concept_id"])


def test_non_positive_response_time_becomes_missing():
    df, _ = assist2009.clean(_raw(ROWS))
    assert np.isnan(df.loc[df["item_id"] == "2", "response_ms"].item())


def test_include_scaffolding_keeps_original_zero_rows():
    cfg = assist2009.CleaningConfig(include_scaffolding=True)
    df, _ = assist2009.clean(_raw(ROWS), cfg)
    assert "7" in set(df["item_id"])


def test_output_has_no_timestamps():
    df, _ = assist2009.clean(_raw(ROWS))
    assert df["timestamp"].isna().all()


def test_validate_rejects_unsorted_rows():
    df, _ = assist2009.clean(_raw(ROWS))
    with pytest.raises(SchemaError, match="sorted"):
        validate(df.iloc[[1, 0, 2, 3]].reset_index(drop=True))


def test_validate_rejects_bad_labels():
    df, _ = assist2009.clean(_raw(ROWS))
    df.loc[0, "correct"] = 2
    with pytest.raises(SchemaError, match="0 or 1"):
        validate(df)
