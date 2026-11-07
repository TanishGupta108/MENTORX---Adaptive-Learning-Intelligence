"""FR-DIAG, FR-QUIZ, FR-KT-03: the adaptive quiz engine end to end, on the real model."""

from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import (
    Attempt,
    Concept,
    Enrollment,
    Mastery,
    ModelVersion,
    Question,
    StudySession,
    User,
)
from tests.conftest import auth, register

S = "/api/v1/sessions"


def _start(client, h, type_="diagnostic", concept=None):
    body = {"subject": "ML", "type": type_}
    if concept:
        body["concept"] = concept
    r = client.post(S, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _correct_key(db, qid):
    return db.get(Question, qid).correct_key


def test_diagnostic_end_to_end(client, db, student):
    sid = _start(client, student)
    concepts = client.get("/api/v1/subjects/ML/concepts", headers=student).json()
    seen = []
    for i in range(19):
        q = client.post(f"{S}/{sid}/next", headers=student).json()
        assert q["position"] == i + 1 and q["total"] == 19
        assert set(q) >= {"stem", "options"} and "correct_key" not in q and "explanation" not in q
        seen.append(q["concept"])
        key = (
            _correct_key(db, q["question_id"]) if i % 2 == 0 else None
        )  # alternate right / "don't know"
        r = client.post(
            f"{S}/{sid}/answer",
            headers=student,
            json={"question_id": q["question_id"], "selected_key": key},
        ).json()
        assert (
            r["feedback"] is None and r["mastery"] is None
        )  # no per-question feedback (FR-DIAG-03)
        assert r["session_complete"] == (i == 18)
    # one question per concept, in prerequisite order (FR-DIAG-01)
    assert seen == [c["code"] for c in concepts]
    assert len(r["summary"]["weakest"]) == 3 and len(r["summary"]["strongest"]) == 3

    user = db.scalar(select(User))
    assert db.scalar(select(Enrollment)).diagnostic_completed_at is not None
    # mastery for every concept (FR-DIAG-04), from the active ML model
    rows = db.scalars(select(Mastery).where(Mastery.user_id == user.id)).all()
    assert len(rows) == 19 and all(0 < m.p_mastery < 1 for m in rows)
    gbm = db.scalar(select(ModelVersion).where(ModelVersion.is_active))
    assert gbm.model_type == "gbm" and all(m.model_version_id == gbm.id for m in rows)
    # every attempt carries the prediction made before the answer (FR-QUIZ-05)
    attempts = db.scalars(select(Attempt)).all()
    assert len(attempts) == 19
    assert all(a.predicted_p_correct is not None and a.model_version_id == gbm.id for a in attempts)
    assert sum(a.is_correct for a in attempts) == 10  # the "don't know" answers count as incorrect
    # can't take it twice
    r = client.post(S, headers=student, json={"subject": "ML", "type": "diagnostic"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "diagnostic_done"


def test_session_and_served_question_are_resumed(client, student):
    sid = _start(client, student)
    q1 = client.post(f"{S}/{sid}/next", headers=student).json()
    assert _start(client, student) == sid
    q_again = client.post(f"{S}/{sid}/next", headers=student).json()
    assert q_again["question_id"] == q1["question_id"]


def test_answer_must_match_served_question_and_only_once(client, db, student):
    sid = _start(client, student)
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    wrong = client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"] + 1000, "selected_key": "A"},
    )
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "question_mismatch"
    ok = client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "A"},
    )
    assert ok.status_code == 200
    again = client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "A"},
    )
    assert again.status_code == 409
    assert db.scalar(select(func.count()).select_from(Attempt)) == 1


def test_practice_on_a_concept_gives_feedback_and_never_repeats(client, db, student):
    sid = _start(client, student, "practice", "ml.regularization")
    concept_id = db.scalar(select(Concept.id).where(Concept.code == "ml.regularization"))
    served = []
    for _ in range(10):
        q = client.post(f"{S}/{sid}/next", headers=student).json()
        served.append(q["question_id"])
        row = db.get(Question, q["question_id"])
        assert row.concept_id == concept_id and row.test_form is None  # never a pre/post-test item
        r = client.post(
            f"{S}/{sid}/answer",
            headers=student,
            json={"question_id": q["question_id"], "selected_key": row.correct_key},
        ).json()
        assert r["feedback"]["correct"] is True and r["feedback"]["correct_key"] == row.correct_key
        assert r["feedback"]["explanation"] == row.explanation
        assert r["mastery"]["concept"] == "ml.regularization" and 0 < r["mastery"]["after"] < 1
    assert r["session_complete"] is True
    assert len(set(served)) == 10  # no repeats within a session (FR-QUIZ-03)


def test_correct_answers_raise_mastery(client, db, student):
    sid = _start(client, student, "practice", "ml.knn")
    firsts, lasts = None, None
    for _ in range(6):
        q = client.post(f"{S}/{sid}/next", headers=student).json()
        r = client.post(
            f"{S}/{sid}/answer",
            headers=student,
            json={
                "question_id": q["question_id"],
                "selected_key": _correct_key(db, q["question_id"]),
            },
        ).json()
        firsts = firsts if firsts is not None else r["mastery"]["after"]
        lasts = r["mastery"]["after"]
    assert lasts > firsts


def test_recommended_practice_works_without_focus(client, student):
    sid = _start(client, student, "practice")
    q = client.post(f"{S}/{sid}/next", headers=student)
    assert q.status_code == 200 and q.json()["concept"].startswith("ml.")


def test_response_time_is_measured_on_the_server(client, db, student):
    sid = _start(client, student, "practice", "ml.svm")
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    session = db.get(StudySession, sid)
    session.current_served_at -= timedelta(seconds=12)  # pretend the student thought for 12 s
    db.commit()
    client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "B"},
    )
    a = db.scalar(select(Attempt))
    assert 12000 <= a.response_ms < 20000 and a.is_valid is True


def test_instant_answers_do_not_count_as_valid(client, db, student):
    sid = _start(client, student, "practice", "ml.svm")
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "B"},
    )
    assert db.scalar(select(Attempt)).is_valid is False  # FR-ENG-02


def test_control_group_still_records_predictions(client, db, student):
    db.execute(User.__table__.update().values(experiment_group="control"))
    db.commit()
    sid = _start(client, student, "practice", "ml.clustering")
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "A"},
    )
    assert db.scalar(select(Attempt)).predicted_p_correct is not None


def test_must_be_enrolled(client, seeded):
    h = auth(register(client, email="lurker@example.com"))
    r = client.post(S, headers=h, json={"subject": "ML", "type": "diagnostic"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_enrolled"


def test_sessions_are_private(client, student):
    sid = _start(client, student)
    other = auth(register(client, email="other@example.com"))
    assert client.post(f"{S}/{sid}/next", headers=other).status_code == 404
    assert client.get(f"{S}/{sid}", headers=other).status_code == 404


def test_ending_the_diagnostic_early_still_builds_a_profile(client, db, student):
    sid = _start(client, student)
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": None},
    )
    r = client.post(f"{S}/{sid}/end", headers=student)
    assert r.json()["status"] == "completed"
    assert db.scalar(select(func.count()).select_from(Mastery)) == 19  # FR-DIAG-05


def test_history_lists_sessions_with_scores(client, db, student):
    sid = _start(client, student, "practice", "ml.svm")
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    client.post(
        f"{S}/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": _correct_key(db, q["question_id"])},
    )
    hist = client.get(S, headers=student).json()
    assert hist[0]["id"] == sid and hist[0]["answered"] == 1 and hist[0]["correct"] == 1
