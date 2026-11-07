import io
import zipfile

import pandas as pd

from mentorx_ml.data import ednet

QUESTIONS = pd.DataFrame(
    {
        "question_id": ["q1", "q2", "q3"],
        "bundle_id": ["b1", "b1", "b2"],
        "correct_answer": ["a", "b", "c"],
        "part": ["1", "1", "5"],
        "tags": ["1;2", "1;2", "7"],
    }
)


def _raw():
    return pd.DataFrame(
        {
            "user_id": ["u1"] * 4 + ["u2"],
            "timestamp": [2000, 1000, 1000, 3000, 500],
            "solving_id": [2, 1, 1, 3, 1],
            "question_id": ["q3", "q1", "q2", "q999", "q1"],
            "user_answer": ["c", "a", "a", "d", None],
            "elapsed_time": [4000, 0, 3000, 1000, 2000],
            "file_row": [2, 0, 1, 3, 0],
        }
    )


def test_clean_orders_by_time_then_file_order_and_marks_correctness():
    df, report = ednet.clean(_raw(), QUESTIONS)
    assert list(df["item_id"]) == ["q1", "q2", "q3"]
    assert list(df["correct"]) == [1, 0, 1]  # a==a, a!=b, c==c
    assert list(df["seq"]) == [0, 1, 2]
    # unknown question q999 and the unanswered row are removed
    assert [rows for _, rows, _ in report.steps] == [5, 4, 3]


def test_concept_is_full_tag_set_and_time_is_kept():
    df, _ = ednet.clean(_raw(), QUESTIONS)
    assert list(df["concept_id"]) == ["1;2", "1;2", "7"]
    assert df["timestamp"].notna().all()
    assert pd.isna(df.loc[0, "response_ms"])  # elapsed_time 0 -> missing


def test_sample_students_is_reproducible(tmp_path):
    path = tmp_path / "kt1.zip"
    with zipfile.ZipFile(path, "w") as z:
        for u in range(20):
            buf = io.StringIO()
            pd.DataFrame(
                {
                    "timestamp": [1],
                    "solving_id": [1],
                    "question_id": ["q1"],
                    "user_answer": ["a"],
                    "elapsed_time": [1000],
                }
            ).to_csv(buf, index=False)
            z.writestr(f"KT1/u{u}.csv", buf.getvalue())
    cfg = ednet.SampleConfig(n_students=5, seed=1)
    a, total = ednet.sample_students(path, cfg)
    b, _ = ednet.sample_students(path, cfg)
    assert total == 20
    assert a["user_id"].nunique() == 5
    assert set(a["user_id"]) == set(b["user_id"])
