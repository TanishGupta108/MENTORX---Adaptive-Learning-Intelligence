import numpy as np
import pandas as pd
import pytest

from mentorx_ml import eda


def _df():
    # student a: concept x -> 0, 1, 1 ; concept y -> 1
    # student b: concept x -> 1, 0
    return pd.DataFrame(
        {
            "student_id": ["a", "a", "a", "a", "b", "b"],
            "item_id": ["1", "2", "3", "4", "1", "2"],
            "concept_id": ["x", "x", "y", "x", "x", "x"],
            "correct": [0, 1, 1, 1, 1, 0],
            "seq": [0, 1, 2, 3, 0, 1],
            "timestamp": pd.NaT,
            "response_ms": [1000.0, 5000.0, np.nan, 8000.0, 2000.0, 4000.0],
        }
    )


def test_opportunity_index_counts_per_student_and_concept():
    assert list(eda.opportunity_index(_df())) == [1, 2, 1, 3, 1, 2]


def test_learning_curve_pools_by_opportunity():
    curve = eda.learning_curve(_df()).set_index("opportunity")
    # opportunity 1: a/x=0, a/y=1, b/x=1 -> 2/3
    assert curve.loc[1, "n"] == 3
    assert curve.loc[1, "p_correct"] == pytest.approx(2 / 3)
    # opportunity 2: a/x=1, b/x=0 -> 1/2
    assert curve.loc[2, "p_correct"] == pytest.approx(0.5)
    assert (curve["ci_low"] <= curve["p_correct"]).all()
    assert (curve["p_correct"] <= curve["ci_high"]).all()


def test_conditional_on_previous_uses_same_concept_only():
    cond = eda.conditional_on_previous(_df()).set_index("previous")
    # after a correct answer on the same concept: a/x seq3 (prev 1) =1, b/x seq1 (prev 1) =0
    assert cond.loc["previous correct", "n"] == 2
    assert cond.loc["previous correct", "p_correct"] == pytest.approx(0.5)
    # after an incorrect answer: a/x seq1 (prev 0) = 1
    assert cond.loc["previous incorrect", "p_correct"] == pytest.approx(1.0)
    assert cond.loc["first attempt", "n"] == 3


def test_rapid_responses_ignores_missing_times():
    r = eda.rapid_responses(_df(), threshold_ms=3000)
    # known times: 1000(0) 5000(1) 8000(1) 2000(1) 4000(0) -> fast: 1000, 2000
    assert r["n_fast"] == 2
    assert r["share_fast"] == pytest.approx(2 / 5)
    assert r["p_correct_fast"] == pytest.approx(0.5)


def test_summary_counts():
    s = eda.summary(_df())
    assert s["students"] == 2
    assert s["concepts"] == 2
    assert s["has_timestamps"] is False
