"""FR-DASH-01..08, FR-QUIZ-11: dashboard numbers come from real attempts, never placeholders."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db.models import Question, QuestionFlag
from tests.api.test_learning import _answer_all, _diagnostic

D = "/api/v1/dashboard"


def test_empty_states_have_no_numbers(client, student):
    d = client.get(f"{D}?subject=ML", headers=student).json()
    assert d["mean_mastery"] is None and d["accuracy"] is None
    assert d["questions_answered"] == 0 and d["concepts_assessed"] == 0
    assert d["strongest"] == [] and d["weakest"] == [] and d["concepts_total"] == 19
    t = client.get(f"{D}/trends?subject=ML", headers=student).json()
    assert len(t["points"]) == 30
    assert all(p["answered"] == 0 and p["accuracy"] is None for p in t["points"])
    assert all(p["mean_mastery"] is None for p in t["points"])
    a = client.get(f"{D}/activity", headers=student).json()
    assert len(a["days"]) == 84 and sum(x["answered"] for x in a["days"]) == 0


def test_numbers_match_the_students_real_data(client, db, student):
    _diagnostic(client, db, student)  # 19 answers, every other one correct
    d = client.get(f"{D}?subject=ML", headers=student).json()
    concepts = client.get("/api/v1/subjects/ML/concepts", headers=student).json()
    masteries = [c["mastery"] for c in concepts]
    assert d["diagnostic_completed"] and d["concepts_assessed"] == 19
    assert d["mean_mastery"] == pytest.approx(sum(masteries) / 19)
    assert d["concepts_mastered"] == sum(m >= 0.8 for m in masteries)
    assert d["questions_answered"] == 19 and d["accuracy"] == pytest.approx(10 / 19)
    assert d["sessions_completed"] == 1
    assert d["strongest"] == []  # nobody has 3 attempts on a concept yet (FR-DASH-03)

    sid = client.post(
        "/api/v1/sessions",
        headers=student,
        json={"subject": "ML", "type": "practice", "concept": "ml.knn"},
    ).json()["id"]
    _answer_all(client, db, student, sid)
    d = client.get(f"{D}?subject=ML", headers=student).json()
    assert (
        [c["concept"] for c in d["strongest"]] == ["ml.knn"] == [c["concept"] for c in d["weakest"]]
    )
    assert d["strongest"][0]["n_attempts"] == 11

    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
    t = client.get(f"{D}/trends?subject=ML&days=7", headers=student).json()["points"]
    assert t[-1]["day"] == today and t[-1]["answered"] == 29
    assert t[-1]["accuracy"] == pytest.approx(15 / 29)
    assert t[-1]["mean_mastery"] == pytest.approx(
        sum(
            c["mastery"] for c in client.get("/api/v1/subjects/ML/concepts", headers=student).json()
        )
        / 19
    )
    a = client.get(f"{D}/activity?weeks=1", headers=student).json()["days"]
    assert a[-1] == {"day": today, "answered": 29}

    history = client.get("/api/v1/sessions", headers=student).json()
    assert history[0]["changes"][0]["concept"] == "ml.knn"  # FR-DASH-05
    assert history[1]["type"] == "diagnostic" and history[1]["changes"] is None


@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])  # UTC+14, UTC-11
def test_days_are_the_students_local_days(client, db, student, tz):
    client.patch("/api/v1/me", headers=student, json={"timezone": tz})
    sid = client.post(
        "/api/v1/sessions",
        headers=student,
        json={"subject": "ML", "type": "practice", "concept": "ml.svm"},
    ).json()["id"]
    q = client.post(f"/api/v1/sessions/{sid}/next", headers=student).json()
    client.post(
        f"/api/v1/sessions/{sid}/answer",
        headers=student,
        json={"question_id": q["question_id"], "selected_key": "A"},
    )
    local = datetime.now(UTC).astimezone(ZoneInfo(tz)).date().isoformat()
    a = client.get(f"{D}/activity?weeks=1", headers=student).json()
    assert a["timezone"] == tz and a["days"][-1] == {"day": local, "answered": 1}


def test_flagging_needs_a_question_you_have_seen(client, db, student):
    unseen = db.scalar(select(Question.id).limit(1))
    r = client.post(f"/api/v1/questions/{unseen}/flag", headers=student, json={})
    assert r.status_code == 404
    sid = client.post(
        "/api/v1/sessions", headers=student, json={"subject": "ML", "type": "practice"}
    ).json()["id"]
    q = client.post(f"/api/v1/sessions/{sid}/next", headers=student).json()
    r = client.post(
        f"/api/v1/questions/{q['question_id']}/flag",
        headers=student,
        json={"comment": "  Option C looks right too  "},
    )
    assert r.status_code == 201 and r.json()["status"] == "open"
    assert db.scalar(select(QuestionFlag)).comment == "Option C looks right too"


def test_dashboard_needs_login_and_enrolment(client, seeded):
    assert client.get(f"{D}?subject=ML").status_code == 401
