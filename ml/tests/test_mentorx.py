import pandas as pd
import pytest

from mentorx_ml.data import mentorx


def _export():
    """Rows shaped like the backend's /admin/export/attempts.csv (pilot.export_attempts)."""
    rows = [
        # student, attempt_id, timestamp, session_type, question, concept, correct, ms, valid
        ("s1", 3, "2026-11-10T10:00:05+00:00", "practice", "knn-002", "ml.knn", 0, 8000, 1),
        ("s1", 1, "2026-11-10T10:00:00+00:00", "pretest", "knn-014", "ml.knn", 1, 9000, 1),
        ("s1", 2, "2026-11-10T10:00:00+00:00", "practice", "knn-003", "ml.knn", 1, 1200, 0),
        ("s1", 4, "2026-11-10T10:01:00+00:00", "practice", "svm-002", "ml.svm", 1, 0, 1),
        ("s1", 5, "2026-11-10T10:02:00+00:00", "practice", "svm-003", "ml.svm", 0, 5000, 1),
        ("s1", 6, "2026-11-10T10:03:00+00:00", "posttest", "svm-015", "ml.svm", 1, 7000, 1),
        ("s2", 7, "2026-11-10T11:00:00+00:00", "practice", "knn-002", "ml.knn", 1, 6000, 1),
    ]
    df = pd.DataFrame(rows, columns=mentorx.EXPORT_COLUMNS)
    df["group"], df["question_version"], df["difficulty"] = "adaptive", 1, 2
    extra = {"dont_know": 0, "attempt_no": 1, "predicted_p_correct": 0.6, "model_version": "v1"}
    return df.assign(**extra)


def test_clean_orders_filters_and_matches_the_canonical_schema():
    df, report = mentorx.clean(_export())
    # s1: invalid fast answer dropped; s2 has too few answers (< 5) and is dropped.
    assert list(df["student_id"].unique()) == ["s1"]
    assert list(df["item_id"]) == ["knn-014", "knn-002", "svm-002", "svm-003", "svm-015"]
    assert list(df["seq"]) == [0, 1, 2, 3, 4]
    assert list(df["correct"]) == [1, 0, 1, 0, 1]
    assert pd.isna(df.loc[2, "response_ms"])  # 0 ms means unknown
    assert set(df["source"]) == {"mentorx"}
    assert [rows for _, rows, _ in report.steps] == [7, 6, 5]


def test_options_keep_invalid_answers_or_drop_tests():
    keep_all, _ = mentorx.clean(_export(), mentorx.CleaningConfig(drop_invalid=False))
    assert len(keep_all) == 6 and keep_all.loc[1, "item_id"] == "knn-003"  # tie broken by id
    practice, _ = mentorx.clean(
        _export(), mentorx.CleaningConfig(include_tests=False, min_answers=1)
    )
    assert not practice["item_id"].isin(["knn-014", "svm-015"]).any()


def test_load_raw_rejects_the_wrong_file(tmp_path):
    p = tmp_path / "outcomes.csv"
    pd.DataFrame({"student": ["s1"], "gain": [0.1]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="attempts export"):
        mentorx.load_raw(p)
