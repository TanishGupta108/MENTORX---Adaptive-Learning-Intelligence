"""M10: daily goal and streak (FR-ENG-01..03), weekly report (FR-ENG-05), feedback (FR-PILOT-03)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.models import Feedback, GoalDay, MasterySnapshot, User
from tests.api.test_learning import _answer_all, _diagnostic

E = "/api/v1/engagement"
S = "/api/v1/sessions"


@pytest.fixture
def all_answers_valid(monkeypatch):
    """Test answers arrive in milliseconds; treat them as valid (FR-ENG-02 minimum = 0)."""
    monkeypatch.setattr(get_settings(), "valid_answer_min_ms", 0)


def _practice(client, h, concept="ml.knn"):
    return client.post(
        S, headers=h, json={"subject": "ML", "type": "practice", "concept": concept}
    ).json()["id"]


def _answer(client, h, sid, key="A"):
    q = client.post(f"{S}/{sid}/next", headers=h).json()
    return client.post(
        f"{S}/{sid}/answer", headers=h, json={"question_id": q["question_id"], "selected_key": key}
    ).json()


def _today():
    return datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()


def test_new_student_has_no_streak(client, student):
    s = client.get(f"{E}/streak", headers=student).json()
    assert s["daily_goal"] == 10 and s["today_valid"] == 0
    assert s["current_streak"] == 0 and s["longest_streak"] == 0
    assert not s["goal_met_today"] and s["timezone"] == "Asia/Kolkata"


def test_reaching_the_goal_counts_today_once(client, db, student, all_answers_valid):
    client.patch("/api/v1/me", headers=student, json={"daily_goal": 3})
    sid = _practice(client, student)
    results = [_answer(client, student, sid) for _ in range(4)]
    goals = [r["goal"] for r in results]
    assert [g["today_valid"] for g in goals] == [1, 2, 3, 4]
    assert [g["just_met"] for g in goals] == [False, False, True, False]  # celebrated once
    assert goals[2]["goal_met_today"] and goals[2]["current_streak"] == 1

    s = client.get(f"{E}/streak", headers=student).json()
    assert s["current_streak"] == 1 == s["longest_streak"] and s["goal_met_today"]
    assert db.scalars(select(GoalDay)).one().goal == 3  # the goal in force at the time


def test_fast_answers_dont_count(client, student):
    """Without the fixture, millisecond test answers are under the 3 s minimum."""
    client.patch("/api/v1/me", headers=student, json={"daily_goal": 1})
    r = _answer(client, student, _practice(client, student))
    assert r["goal"]["today_valid"] == 0 and not r["goal"]["goal_met_today"]


def test_streak_continues_from_previous_days(client, db, student, all_answers_valid):
    user = db.scalar(select(User))
    today = _today()
    for back in (1, 2, 5):
        db.add(GoalDay(user_id=user.id, day=today - timedelta(days=back), goal=10))
    db.commit()
    s = client.get(f"{E}/streak", headers=student).json()
    assert s["current_streak"] == 2 and s["longest_streak"] == 2  # alive until today ends

    client.patch("/api/v1/me", headers=student, json={"daily_goal": 1})
    r = _answer(client, student, _practice(client, student))
    assert r["goal"]["just_met"] and r["goal"]["current_streak"] == 3
    assert client.get(f"{E}/streak", headers=student).json()["longest_streak"] == 3


def test_lowering_the_goal_can_complete_today(client, student, all_answers_valid):
    sid = _practice(client, student)
    for _ in range(2):
        _answer(client, student, sid)
    assert not client.get(f"{E}/streak", headers=student).json()["goal_met_today"]
    client.patch("/api/v1/me", headers=student, json={"daily_goal": 2})
    s = client.get(f"{E}/streak", headers=student).json()
    assert s["goal_met_today"] and s["current_streak"] == 1

    # Raising it again doesn't take the day away.
    client.patch("/api/v1/me", headers=student, json={"daily_goal": 50})
    assert client.get(f"{E}/streak", headers=student).json()["goal_met_today"]


def test_weekly_report_empty_state(client, student):
    w = client.get(f"{E}/weekly?subject=ML", headers=student).json()
    assert w["questions"] == 0 and w["accuracy"] is None and w["goal_days_met"] == 0
    assert w["mastery_change"] is None and w["concepts_improved"] == []
    assert w["end"] == _today().isoformat()
    assert w["start"] == (_today() - timedelta(days=6)).isoformat()


def test_weekly_report_uses_real_data(client, db, student):
    _diagnostic(client, db, student)  # 19 answers, every other one correct
    w = client.get(f"{E}/weekly?subject=ML", headers=student).json()
    assert w["questions"] == 19 and w["accuracy"] == pytest.approx(10 / 19)
    assert w["mean_mastery_start"] is None  # no estimate existed before this week

    # Pretend the diagnostic happened 10 days ago, then practise k-NN correctly this week.
    user = db.scalar(select(User))
    db.execute(
        update(MasterySnapshot)
        .where(MasterySnapshot.user_id == user.id)
        .values(created_at=MasterySnapshot.created_at - timedelta(days=10))
    )
    db.commit()
    _answer_all(client, db, student, _practice(client, student), correct_every=1)
    w = client.get(f"{E}/weekly?subject=ML", headers=student).json()
    assert w["mastery_change"] is not None and w["mastery_change"] > 0
    improved = {c["concept"]: c for c in w["concepts_improved"]}
    assert "ml.knn" in improved
    assert improved["ml.knn"]["after"] - improved["ml.knn"]["before"] >= 0.05


def test_feedback_is_stored_and_exported(client, db, student):
    r = client.post(
        "/api/v1/feedback",
        headers=student,
        json={"rating": 4, "category": "idea", "message": "  Add dark mode charts  ", "page": "/"},
    )
    assert r.status_code == 201
    row = db.get(Feedback, r.json()["id"])
    assert (row.rating, row.category, row.message, row.page) == (
        4,
        "idea",
        "Add dark mode charts",
        "/",
    )
    export = client.get("/api/v1/me/export", headers=student).json()
    assert export["feedback"][0]["page"] == "/" and export["goal_days"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 0, "category": "bug"},
        {"rating": 6, "category": "bug"},
        {"rating": 3, "category": "spam"},
        {"rating": 3, "category": "bug", "message": "x" * 2001},
    ],
)
def test_feedback_validation(client, student, body):
    assert client.post("/api/v1/feedback", headers=student, json=body).status_code == 422


def test_feedback_needs_login_and_is_rate_limited(client, student):
    assert client.post("/api/v1/feedback", json={"rating": 3, "category": "bug"}).status_code == 401
    for _ in range(10):
        r = client.post("/api/v1/feedback", headers=student, json={"rating": 3, "category": "bug"})
        assert r.status_code == 201
    r = client.post("/api/v1/feedback", headers=student, json={"rating": 3, "category": "bug"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_account_deletion_removes_goal_days_and_feedback(client, db, student, all_answers_valid):
    client.patch("/api/v1/me", headers=student, json={"daily_goal": 1})
    _answer(client, student, _practice(client, student))
    client.post("/api/v1/feedback", headers=student, json={"rating": 5, "category": "other"})
    me = client.get("/api/v1/me", headers=student).json()
    r = client.request("DELETE", "/api/v1/me", headers=student, json={"confirm_email": me["email"]})
    assert r.status_code == 204
    db.expire_all()
    assert db.scalars(select(GoalDay)).all() == [] and db.scalars(select(Feedback)).all() == []
