"""M11 pilot: FR-PILOT-01/02/04/05, FR-DASH-09, FR-QUIZ-10."""

import csv
import io

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Enrollment, Question, StudySession, User
from app.services.pilot import pseudonym, sus_score
from tests.conftest import auth, register

S = "/api/v1/sessions"
P = "/api/v1/pilot"


def _participant(client, db, h, group="adaptive", form="A", consent=True):
    user = db.scalar(select(User).where(User.email == "student@example.com"))
    user.experiment_group, user.pretest_form = group, form
    db.commit()
    if consent:
        client.patch("/api/v1/me", headers=h, json={"consent_research": True})
    return user


def _take(client, db, h, kind, correct_every=1):
    """Run a fixed-list session to the end. Returns (session id, served question ids, results)."""
    r = client.post(S, headers=h, json={"subject": "ML", "type": kind})
    assert r.status_code == 201, r.text
    sid, served, results, i = r.json()["id"], [], [], 0
    while True:
        q = client.post(f"{S}/{sid}/next", headers=h)
        if q.status_code != 200:
            return sid, served, results
        qid = q.json()["question_id"]
        served.append(qid)
        key = db.get(Question, qid).correct_key if i % correct_every == 0 else None
        results.append(
            client.post(
                f"{S}/{sid}/answer", headers=h, json={"question_id": qid, "selected_key": key}
            ).json()
        )
        i += 1


@pytest.fixture
def posttest_open(monkeypatch):
    monkeypatch.setattr(get_settings(), "posttest_open", True)


def test_registration_assigns_group_and_form_only_while_pilot_runs(client, db, seeded, monkeypatch):
    from app.services.auth import register_limiter

    monkeypatch.setattr(register_limiter, "limit", 100)  # 31 sign-ups from one test client
    register(client, email="before@example.com")
    monkeypatch.setattr(get_settings(), "pilot_active", True)
    for i in range(30):
        register(client, email=f"p{i}@example.com")
    users = {u.email: u for u in db.scalars(select(User))}
    before = users.pop("before@example.com")
    assert before.experiment_group is None and before.pretest_form is None
    assert {u.experiment_group for u in users.values()} == {"adaptive", "control"}
    assert {u.pretest_form for u in users.values()} == {"A", "B"}  # P(fail) ~ 4e-9


def test_tests_are_only_for_consenting_participants(client, db, student):
    r = client.post(S, headers=student, json={"subject": "ML", "type": "pretest"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_in_pilot"
    _participant(client, db, student, consent=False)
    assert (
        client.post(S, headers=student, json={"subject": "ML", "type": "pretest"}).status_code
        == 403
    )
    s = client.get(f"{P}/status?subject=ML", headers=student).json()
    assert s["in_study"] and not s["consented"] and s["pretest"]["status"] == "unavailable"


def test_pretest_uses_its_form_and_replaces_the_diagnostic(client, db, student):
    _participant(client, db, student, form="B")
    s = client.get(f"{P}/status?subject=ML", headers=student).json()
    assert s["pretest"] == {"status": "todo", "session_id": None, "questions": 19}
    assert "group" not in s  # students are never told their group

    r = client.post(S, headers=student, json={"subject": "ML", "type": "diagnostic"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "pretest_first"

    sid, served, results = _take(client, db, student, "pretest", correct_every=2)
    forms = {db.get(Question, q).test_form for q in served}
    assert len(served) == 19 and forms == {"B"}
    assert all(r["feedback"] is None and r["mastery"] is None for r in results)  # no feedback
    assert results[-1]["session_complete"] and results[-1]["summary"]["weakest"]

    user = db.scalar(select(User))
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id))
    assert enrollment.diagnostic_completed_at is not None  # profile set up from the pre-test
    assert client.get("/api/v1/learning-path?subject=ML", headers=student).json()["items"]
    s = client.get(f"{P}/status?subject=ML", headers=student).json()
    assert s["pretest"]["status"] == "done" and s["posttest"]["status"] == "unavailable"
    r = client.post(S, headers=student, json={"subject": "ML", "type": "pretest"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "pretest_done"


def test_test_questions_never_appear_in_practice(client, db, student):
    _participant(client, db, student)
    _take(client, db, student, "pretest")
    r = client.post(
        S, headers=student, json={"subject": "ML", "type": "practice", "concept": "ml.knn"}
    ).json()
    for _ in range(10):
        q = client.post(f"{S}/{r['id']}/next", headers=student)
        if q.status_code != 200:
            break
        assert db.get(Question, q.json()["question_id"]).test_form is None
        client.post(
            f"{S}/{r['id']}/answer",
            headers=student,
            json={"question_id": q.json()["question_id"], "selected_key": None},
        )


def test_posttest_opens_at_the_end_and_uses_the_other_form(client, db, student, monkeypatch):
    _participant(client, db, student, form="A")
    r = client.post(S, headers=student, json={"subject": "ML", "type": "posttest"})
    assert r.json()["error"]["code"] == "pretest_first"
    _take(client, db, student, "pretest")
    r = client.post(S, headers=student, json={"subject": "ML", "type": "posttest"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "posttest_closed"

    monkeypatch.setattr(get_settings(), "posttest_open", True)
    assert (
        client.get(f"{P}/status?subject=ML", headers=student).json()["posttest"]["status"] == "todo"
    )
    _, served, results = _take(client, db, student, "posttest")
    assert {db.get(Question, q).test_form for q in served} == {"B"} and len(served) == 19
    assert results[-1]["session_complete"] and results[-1]["summary"] is None
    s = client.get(f"{P}/status?subject=ML", headers=student).json()
    assert s["posttest"]["status"] == "done" and not s["sus_done"]


@pytest.mark.parametrize(
    ("answers", "score"),
    [
        ([3] * 10, 50.0),
        ([5, 1] * 5, 100.0),
        ([1, 5] * 5, 0.0),
        ([4, 2, 4, 2, 4, 2, 4, 2, 4, 2], 75.0),
    ],
)
def test_sus_scoring(answers, score):
    assert sus_score(answers) == score


def test_sus_after_posttest_once(client, db, student, posttest_open):
    _participant(client, db, student)
    body = {"answers": [4, 2] * 5, "comment": " Nice "}
    r = client.post(f"{P}/sus?subject=ML", headers=student, json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "posttest_first"
    _take(client, db, student, "pretest")
    _take(client, db, student, "posttest")
    bad = client.post(f"{P}/sus?subject=ML", headers=student, json={"answers": [6] + [3] * 9})
    assert bad.status_code == 422
    r = client.post(f"{P}/sus?subject=ML", headers=student, json=body)
    assert r.status_code == 201 and r.json()["score"] == 75.0
    assert client.get(f"{P}/status?subject=ML", headers=student).json()["sus_done"]
    assert client.post(f"{P}/sus?subject=ML", headers=student, json=body).status_code == 409


def test_admin_metrics_and_exports(client, db, student, monkeypatch, posttest_open):
    me = _participant(client, db, student, group="adaptive")
    _take(client, db, student, "pretest", correct_every=2)  # 10 / 19
    _take(client, db, student, "posttest", correct_every=1)  # 19 / 19
    client.post(f"{P}/sus?subject=ML", headers=student, json={"answers": [5, 1] * 5})
    client.post("/api/v1/feedback", headers=student, json={"rating": 4, "category": "idea"})

    # A non-consenting student must not appear in research outputs.
    other = auth(register(client, email="nope@example.com"))
    client.post("/api/v1/subjects/ML/enroll", headers=other)

    assert client.get("/api/v1/admin/pilot/metrics", headers=student).status_code == 403
    monkeypatch.setattr(get_settings(), "admin_emails", "Boss@Example.com")
    admin = auth(register(client, email="boss@example.com"))
    assert client.get("/api/v1/me", headers=admin).json()["role"] == "admin"

    m = client.get("/api/v1/admin/pilot/metrics", headers=admin).json()
    adaptive = next(g for g in m["groups"] if g["group"] == "adaptive")
    assert adaptive["participants"] == 1 and adaptive["posttest_done"] == 1
    assert adaptive["mean_pre"] == pytest.approx(10 / 19) and adaptive["mean_post"] == 1.0
    assert adaptive["mean_gain"] == pytest.approx(9 / 19) and adaptive["gain_ci95"] is None
    assert adaptive["sus_mean"] == 100.0 and m["gain_difference"] is None  # n too small
    assert m["engagement"]["students"] == 2 and m["engagement"]["wau"] == 1  # admin excluded
    assert m["model"]["n"] == 38 and m["model"]["bins"]
    assert m["feedback"]["n"] == 1 and m["feedback"]["recent"][0]["rating"] == 4

    r = client.get("/api/v1/admin/export/attempts.csv", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 38 and {x["student"] for x in rows} == {pseudonym(me.id)}
    assert {x["session_type"] for x in rows} == {"pretest", "posttest"}
    assert "student@example.com" not in r.text and "Asha" not in r.text

    out = list(
        csv.DictReader(
            io.StringIO(client.get("/api/v1/admin/export/outcomes.csv", headers=admin).text)
        )
    )
    assert len(out) == 1 and out[0]["group"] == "adaptive"
    assert float(out[0]["gain"]) == pytest.approx(9 / 19) and float(out[0]["sus"]) == 100.0


def test_gain_difference_between_groups():
    from app.services.pilot import _welch

    diff, ci, d = _welch([0.3, 0.4, 0.5, 0.4], [0.1, 0.2, 0.15, 0.25])
    assert diff == pytest.approx(0.225)
    assert ci[0] < diff < ci[1] and ci[0] > 0  # clearly separated groups
    assert d > 1


def test_sessions_by_type_are_listed(client, db, student):
    _participant(client, db, student)
    _take(client, db, student, "pretest")
    history = client.get(S, headers=student).json()
    assert history[0]["type"] == "pretest" and history[0]["changes"] is None
    assert db.scalar(select(StudySession.status)) == "completed"
