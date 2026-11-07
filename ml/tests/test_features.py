"""Leakage tests: a feature for row t may depend only on rows before t (same student)
and on difficulty learned from OTHER training students."""

import numpy as np
import pandas as pd
import pytest

from mentorx_ml.features import (
    HISTORY_FEATURES,
    DifficultyTable,
    difficulty_features,
    history_features,
)


def _frame(n_students=30, per_student=12, seed=0, with_time=False):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n_students):
        for t in range(per_student):
            rows.append(
                {
                    "student_id": f"s{s}",
                    "item_id": f"i{rng.integers(0, 15)}",
                    "concept_id": f"c{rng.integers(0, 3)}",
                    "correct": int(rng.random() < 0.6),
                    "seq": t,
                    "timestamp": pd.Timestamp("2026-01-01", tz="UTC")
                    + pd.Timedelta(minutes=10 * t + s)
                    if with_time
                    else pd.NaT,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize("with_time", [False, True])
def test_history_features_ignore_current_and_future_labels(with_time):
    df = _frame(with_time=with_time)
    base = history_features(df, use_time=with_time)
    flipped = df.copy()
    # flip the label of the target row and every later row of that student
    later = (flipped["student_id"] == "s3") & (flipped["seq"] >= 6)
    flipped.loc[later, "correct"] = 1 - flipped.loc[later, "correct"]
    after = history_features(flipped, use_time=with_time)
    upto = (df["student_id"] == "s3") & (df["seq"] <= 6)
    pd.testing.assert_frame_equal(base[upto], after[upto])


def test_history_features_ignore_other_students():
    df = _frame()
    base = history_features(df, use_time=False)
    changed = df.copy()
    changed.loc[changed["student_id"] == "s1", "correct"] = 1
    after = history_features(changed, use_time=False)
    others = df["student_id"] != "s1"
    pd.testing.assert_frame_equal(base[others], after[others])


def test_first_attempt_features_are_neutral():
    df = _frame()
    feats = history_features(df, use_time=False)
    first = df.groupby("student_id").cumcount() == 0
    assert (feats.loc[first, "acc_overall"] == 0.5).all()
    assert (feats.loc[first, "prev_concept"] == 0).all()
    assert (feats.loc[first, "is_first_concept"] == 1).all()


def test_concept_history_counts_only_same_concept():
    df = pd.DataFrame(
        {
            "student_id": ["a"] * 4,
            "item_id": ["1", "2", "3", "4"],
            "concept_id": ["x", "y", "x", "x"],
            "correct": [1, 0, 0, 1],
            "seq": [0, 1, 2, 3],
            "timestamp": pd.NaT,
        }
    )
    f = history_features(df, use_time=False)
    # row 3 (concept x): previous x attempts are rows 0 (1) and 2 (0)
    assert f.loc[3, "acc_concept"] == pytest.approx((1 + 1) / (2 + 2))
    assert f.loc[3, "prev_concept"] == -1
    assert f.loc[3, "log_gap_concept"] == pytest.approx(np.log1p(0))
    assert f.loc[2, "log_gap_concept"] == pytest.approx(np.log1p(1))  # row 1 was concept y


def test_time_features_require_timestamps():
    with pytest.raises(ValueError, match="no timestamps"):
        history_features(_frame(with_time=False), use_time=True)


def test_train_difficulty_is_cross_fitted():
    """A training row's own label must not influence its own difficulty feature."""
    df = _frame(n_students=40)
    feats, _, _ = difficulty_features(df, [], seed=0)
    target = df.index[(df["student_id"] == "s5") & (df["seq"] == 0)][0]
    flipped = df.copy()
    flipped.loc[flipped["student_id"] == "s5", "correct"] = (
        1 - flipped.loc[flipped["student_id"] == "s5", "correct"]
    )
    feats2, _, _ = difficulty_features(flipped, [], seed=0)
    # s5's rows are predicted by a table fitted on other folds -> unchanged
    s5 = df["student_id"] == "s5"
    pd.testing.assert_frame_equal(feats[s5], feats2[s5])
    assert target in feats.index


def test_difficulty_table_backs_off_to_concept_then_global():
    train = pd.DataFrame(
        {"item_id": ["1", "1", "2"], "concept_id": ["x", "x", "x"], "correct": [1, 1, 0]}
    )
    t = DifficultyTable().fit(train)
    unseen_item = pd.DataFrame({"item_id": ["99"], "concept_id": ["x"]})
    unseen_concept = pd.DataFrame({"item_id": ["98"], "concept_id": ["zzz"]})
    assert t.transform(unseen_item)["item_logit"].item() == pytest.approx(
        t.transform(unseen_item)["concept_logit"].item()
    )
    g = np.log(t.global_p / (1 - t.global_p))
    assert t.transform(unseen_concept)["concept_logit"].item() == pytest.approx(g)


def test_feature_list_is_concept_agnostic():
    assert not any("id" in f for f in HISTORY_FEATURES)
