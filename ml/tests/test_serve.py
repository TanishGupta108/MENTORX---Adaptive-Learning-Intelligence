"""D-3: serving features must equal training features exactly, row by row."""

import numpy as np
import pandas as pd
import pytest

from mentorx_ml.features import HISTORY_FEATURES, TIME_FEATURES, history_features
from mentorx_ml.serve import StudentState


def _random_history(seed, n_students=8, max_len=60):
    rng = np.random.default_rng(seed)
    rows = []
    base = pd.Timestamp("2026-01-01", tz="UTC")
    for s in range(n_students):
        t = base
        for q in range(int(rng.integers(1, max_len))):
            # irregular gaps: seconds to weeks, including zero (same bundle)
            t = t + pd.Timedelta(seconds=float(rng.choice([0, 5, 60, 3600, 86400, 604800])))
            rows.append(
                {
                    "student_id": f"s{s}",
                    "item_id": f"i{rng.integers(0, 12)}",
                    "concept_id": f"c{rng.integers(0, 4)}",
                    "correct": int(rng.random() < 0.6),
                    "seq": q,
                    "timestamp": t,
                }
            )
    return pd.DataFrame(rows)


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("use_time", [False, True])
def test_serving_features_equal_training_features(seed, use_time):
    df = _random_history(seed)
    batch = history_features(df, use_time=use_time)
    names = HISTORY_FEATURES + (TIME_FEATURES if use_time else [])
    for _, student in df.groupby("student_id", sort=False):
        state = StudentState()
        for idx, row in student.iterrows():
            served = state.history_row(
                row["concept_id"], row["item_id"], row["timestamp"].to_pydatetime(), use_time
            )
            expected = batch.loc[idx, names]
            np.testing.assert_allclose(
                [served[n] for n in names],
                expected.to_numpy(dtype=float),
                rtol=0,
                atol=1e-12,
                err_msg=f"row {idx}",
            )
            state.update(
                row["concept_id"], row["item_id"], row["correct"], row["timestamp"].to_pydatetime()
            )


def test_time_features_need_current_time():
    with pytest.raises(ValueError):
        StudentState().history_row("c", "i", None, use_time=True)
