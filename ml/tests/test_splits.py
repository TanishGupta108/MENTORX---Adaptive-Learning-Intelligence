import pandas as pd
import pytest

from mentorx_ml.splits import split_by_student


def _attempts(n_students=100, per_student=5):
    return pd.DataFrame(
        {
            "student_id": [s for s in range(n_students) for _ in range(per_student)],
            "correct": [i % 2 for i in range(n_students * per_student)],
        }
    )


def test_no_student_in_two_splits():
    s = split_by_student(_attempts())
    train, val, test = (set(x.student_id) for x in (s.train, s.val, s.test))
    assert not train & val
    assert not train & test
    assert not val & test


def test_every_row_is_kept_exactly_once():
    df = _attempts()
    s = split_by_student(df)
    assert len(s.train) + len(s.val) + len(s.test) == len(df)


def test_fractions_are_respected():
    s = split_by_student(_attempts(n_students=100), val_frac=0.15, test_frac=0.15)
    assert s.test.student_id.nunique() == 15
    assert s.val.student_id.nunique() == 15
    assert s.train.student_id.nunique() == 70


def test_split_is_reproducible():
    a = split_by_student(_attempts(), seed=7)
    b = split_by_student(_attempts(), seed=7)
    assert set(a.test.student_id) == set(b.test.student_id)


def test_bad_fractions_raise():
    with pytest.raises(ValueError):
        split_by_student(_attempts(), val_frac=0.6, test_frac=0.5)
