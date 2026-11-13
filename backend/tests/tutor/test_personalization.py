"""v3 personalization rules: mastery, stuck detection, early stop, reviews, pace suggestion,
grade, honest reassessment outcomes, Home and the SQL budget of the busiest screens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select

from app.core.config import get_settings
from app.db.models import Enrollment, User
from app.db.session import get_engine
from app.tutor import assess, localtime, recommend, state, views
from app.tutor.models import Assessment, Interaction, Item, SkillState
from app.tutor.practice import practice_length
from tests.conftest import auth, register
from tests.tutor.conftest import answer_body
from tests.tutor.test_journey import run_assessment

# ---------------------------------------------------------------- pure rules


def test_mastery_rule_and_to_go():
    assert state.mastery_met([1, 1, 1, 1, 1], 5)
    assert not state.mastery_met([1, 1, 1, 1], 4)  # needs 5 answers
    assert not state.mastery_met([1, 1, 1, 1, 0], 5)  # last 3 must be right
    assert not state.mastery_met([0, 0, 1, 0, 1, 1, 1, 1], 8)  # 5/8 < 80%
    assert state.to_go([1, 1, 1, 1, 1], 5) == 0
    assert state.to_go([], 0) == 5
    assert state.to_go([0, 0], 2) == 7  # needs 7 of the last 8 right
    assert state.to_go([1, 1, 1, 0], 4) == 3


def test_mastery_info_hints():
    st = SkillState(attempts=6, recent=[0, 1, 1, 1, 1, 1], completed_at=None, mastered_at=None)
    info = state.mastery_info(st)
    assert info["mastered"] and info["progress_hint"] == "Mastered: take the 5-question check"
    st.recent, st.attempts = [1, 0, 1], 3
    assert state.mastery_info(st)["progress_hint"] == "2 more correct to master"
    st.completed_at = datetime.now(UTC)
    assert state.mastery_info(st)["progress_hint"] == "Completed"
    assert state.mastery_info(None)["progress_hint"] is None


def test_stuck_rule():
    recent = [0, 1, 0, 0, 0, 1, 0, 0, 1, 0]
    assert state.is_stuck(10, recent, None)
    assert not state.is_stuck(9, recent, None)  # not enough attempts yet
    assert not state.is_stuck(10, recent, datetime.now(UTC))  # mastered once: not wheel-spinning
    assert not state.is_stuck(10, [0, 0, 0, 0, 1, 1, 1, 1, 0, 1], None)  # recent 4/6


def test_ever_mastered_at():
    t = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(8)]
    assert state.ever_mastered_at(list(zip([1, 1, 1, 1, 1, 0, 0, 0], t, strict=True))) == t[4]
    assert state.ever_mastered_at(list(zip([1, 0] * 4, t, strict=True))) is None


def test_one_wrong_answer_is_not_a_weakness():
    one = state.Evidence(1, 0, [0])
    assert state.diagnose(one, None, 0.75, 0.45) == "developing"
    two = state.Evidence(2, 0, [0, 0])
    assert state.diagnose(two, None, 0.75, 0.45) == "potential_weakness"


def test_pace_suggestion_rule():
    good = [(True, False, False, "s1")] * 10 + [(True, False, False, "s2")] * 10
    assert state.pace_suggestion(good, "balanced") == "challenge"
    assert state.pace_suggestion(good, "challenge") is None
    assert state.pace_suggestion(good[:19], "balanced") is None  # needs 20 answers
    one_session = [(True, False, False, "s1")] * 20
    assert state.pace_suggestion(one_session, "balanced") is None
    hard = [(i % 3 == 0, False, False, f"s{i // 10}") for i in range(20)]
    assert state.pace_suggestion(hard, "balanced") == "more_support"
    reveals = [(i >= 7, False, i < 7, f"s{i // 10}") for i in range(20)]  # 65% right
    assert state.pace_suggestion(reveals, "balanced") == "more_support"


def test_grade_and_lengths():
    assert assess.start_grade(7, [3, 4, 5, 6, 7, 8]) == 6
    assert assess.start_grade(3, [3, 4, 5]) == 3
    assert assess.start_grade(None, [5, 6, 7]) == 5
    assert assess.start_grade(4, [6, 7]) == 6  # nearest available grade
    assert [practice_length(p) for p in ("more_support", "balanced", "challenge")] == [6, 8, 10]
    assert [state.review_interval(n) for n in range(5)] == [3, 7, 14, 30, 60]


def test_local_day_follows_the_user_timezone():
    user = User(timezone="Asia/Kolkata")
    late = datetime(2026, 1, 1, 20, 0, tzinfo=UTC)  # 01:30 on 2 January in India
    assert localtime.local_date(late, localtime.tz_of(user)).isoformat() == "2026-01-02"
    start = localtime.day_start(user, late.date())
    assert start == datetime(2025, 12, 31, 18, 30, tzinfo=UTC)
    assert localtime.tz_of(User(timezone="Not/AZone")) is not None


# ---------------------------------------------------------------- API behaviour


def _user(db) -> User:
    return db.scalar(select(User).where(User.email == "student@example.com"))


def test_three_wrong_at_easy_stops_the_session(client, math_keys, learner):
    h = learner
    p = client.post("/api/v2/practice", json={"skill_id": 217}, headers=h).json()
    assert p["total"] == 8 and p["difficulty"] == "easy"
    for i in range(3):
        q = client.get(f"/api/v2/practice/{p['id']}/next", headers=h).json()
        assert q["selection"]["how"] and "%" not in q["selection"]["how"]
        r = client.post(
            f"/api/v2/practice/{p['id']}/answer",
            json=answer_body(math_keys, q, False),
            headers=h,
        ).json()
        if i < 2:
            assert r["early_stop"] is None and not r["complete"]
    assert r["complete"] and r["early_stop"]["reason"] == "stuck"
    nxt = r["summary"]["next"]
    # 7.EE.B.4a has a curated building block (6.EE.B.7) that isn't strong yet
    assert nxt["action"] == "prerequisite" and nxt["skill_id"] == 166


def test_reassessment_outcomes_are_honest(client, math_keys, learner, db):
    h = learner
    run_assessment(
        client, h, math_keys, {"kind": "reassessment", "skill_id": 129}, lambda i, q: False
    )
    page = client.get("/api/v2/skills/129", headers=h).json()
    assert page["mode"] == "foundation" and page["mode_is_override"]
    assert page["last_reassessment"]["result"]["outcome"] == "not_improved"
    assert page["last_reassessment"]["result"]["message"].startswith("Let's practise")
    _, res = run_assessment(
        client, h, math_keys, {"kind": "reassessment", "skill_id": 129}, lambda i, q: True
    )
    assert res["completed"]
    st = db.get(SkillState, (_user(db).id, 129))
    db.refresh(st)
    assert st.mode_override is None and st.completed_at is not None and st.revision_stage == 0
    due = st.revision_due_at - datetime.now(UTC)
    assert timedelta(days=2, hours=23) < due <= timedelta(days=3)
    # an early (not yet due) pass keeps the review stage
    st.revision_stage = 2
    db.commit()
    run_assessment(
        client, h, math_keys, {"kind": "reassessment", "skill_id": 129}, lambda i, q: True
    )
    db.refresh(st)
    assert st.revision_stage == 2
    # failing a check of a completed skill means it is no longer shown as completed
    run_assessment(
        client, h, math_keys, {"kind": "reassessment", "skill_id": 129}, lambda i, q: False
    )
    db.refresh(st)
    assert st.completed_at is None
    assert client.get("/api/v2/skills/129", headers=h).json()["completed"] is False


def test_initial_accuracy_ignores_mixed_answers(client, math_keys, learner, db):
    user = _user(db)
    multi = db.scalar(select(Item).where(Item.n_skills > 1))
    single = db.scalar(select(Item).where(Item.skill_id == multi.skill_id, Item.n_skills == 1))
    t = datetime.now(UTC) - timedelta(hours=1)
    for item, ok in ((multi, True), (single, False)):
        db.add(
            Interaction(
                user_id=user.id, item_id=item.id, skill_id=item.skill_id, n_skills=item.n_skills,
                context="practice", response={"value": "1"}, is_correct=ok, model_label=ok,
                created_at=t,
            )
        )  # fmt: skip
    db.commit()
    a = Assessment(
        user_id=user.id, subject_id=multi.subject_id, kind="reassessment",
        skill_id=multi.skill_id, planned_item_ids=[], started_at=datetime.now(UTC),
    )  # fmt: skip
    assert assess.initial_accuracy_rows(db, user.id, a) == [False]


def test_reviews_due_are_served_interleaved(client, math_keys, learner, db):
    h = learner
    assert (
        client.post("/api/v2/practice", json={"kind": "review"}, headers=h).json()["error"]["code"]
        == "nothing_due"
    )
    run_assessment(client, h, math_keys, {"kind": "diagnostic"}, lambda i, q: True)
    user = _user(db)
    past = datetime.now(UTC) - timedelta(days=1)
    for sid, days in ((129, 2), (130, 1)):
        st = db.get(SkillState, (user.id, sid))
        st.revision_due_at, st.revision_stage = past - timedelta(days=days), 1
    db.commit()
    home = client.get("/api/v2/home", headers=h).json()
    assert home["reviews_due"]["count"] == 2 and home["next"]["kind"] == "review"
    assert home["next"]["start"] == {"endpoint": "review"}
    p = client.post("/api/v2/practice", json={"kind": "review"}, headers=h).json()
    assert p["kind"] == "review" and p["total"] == 4 and p["skill_id"] is None
    skills = []
    for _ in range(4):
        q = client.get(f"/api/v2/practice/{p['id']}/next", headers=h).json()
        skills.append(q["skill"]["id"])
        r = client.post(
            f"/api/v2/practice/{p['id']}/answer", json=answer_body(math_keys, q, True), headers=h
        ).json()
    assert skills == [129, 130, 129, 130]  # most overdue first, interleaved
    assert r["complete"] and r["summary"]["review"]
    for sid in (129, 130):
        st = db.get(SkillState, (user.id, sid))
        db.refresh(st)
        assert st.revision_stage == 2
        assert st.revision_due_at - datetime.now(UTC) > timedelta(days=13)


def test_home_before_and_after_the_diagnostic(client, math_keys, learner):
    h = learner
    home = client.get("/api/v2/home", headers=h).json()
    assert home["next"]["kind"] == "diagnostic" and home["next"]["skill"] is None
    assert home["next"]["start"] == {
        "endpoint": "assessment",
        "kind": "diagnostic",
        "skill_id": None,
    }
    assert home["up_next"] == [] and home["pace_suggestion"] is None
    run_assessment(client, h, math_keys, {"kind": "diagnostic"}, lambda i, q: i % 2 == 0)
    home = client.get("/api/v2/home", headers=h).json()
    assert home["diagnostic_completed"] and home["diagnosis_summary"]["show"]
    s = home["diagnosis_summary"]
    assert s["strong"] + s["getting_there"] + s["needs_practice"] + s["not_tried"] == 10
    nxt = home["next"]
    assert nxt["kind"] in ("practice", "skill_check", "learn", "prerequisite", "reassess")
    assert nxt["reason"] and nxt["title"] and nxt["start"]["endpoint"]
    assert len(home["up_next"]) <= 2 and nxt not in home["up_next"]
    assert "%" not in nxt["reason"]  # plain words, no model numbers
    # starting a session makes it the resume action
    start = nxt["start"]
    if start["endpoint"] == "practice":
        sess = client.post(
            "/api/v2/practice", json={"skill_id": start["skill_id"], "guided": start["guided"]},
            headers=h,
        ).json()  # fmt: skip
        home = client.get("/api/v2/home", headers=h).json()
        assert home["next"]["kind"] == "resume"
        assert home["next"]["start"] == {"endpoint": "resume_practice", "session_id": sess["id"]}
        assert not home["diagnosis_summary"]["show"]


def test_pace_suggestion_accept_and_dismiss(client, math_keys, learner, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "pace_window", 5)
    h = learner
    run_assessment(client, h, math_keys, {"kind": "diagnostic"}, lambda i, q: True)
    for _ in range(2):  # a second session so the window spans two sessions
        p = client.post("/api/v2/practice", json={"skill_id": 129}, headers=h).json()
        q = client.get(f"/api/v2/practice/{p['id']}/next", headers=h).json()
        client.post(
            f"/api/v2/practice/{p['id']}/answer", json=answer_body(math_keys, q, True), headers=h
        )
        client.post(f"/api/v2/practice/{p['id']}/end", headers=h)
    home = client.get("/api/v2/home", headers=h).json()
    assert home["pace_suggestion"]["suggested"] == "challenge"
    prof = client.post("/api/v2/home/pace-suggestion", json={"accept": True}, headers=h).json()
    assert prof["pace_preference"] == "challenge"
    assert client.get("/api/v2/home", headers=h).json()["pace_suggestion"] is None  # 14 days


def test_grade_drives_the_first_diagnostic_question(client, math_keys):
    h = auth(register(client, email="g8@example.com"))
    r = client.post(
        "/api/v2/onboarding",
        json={"goal_type": "assess_overall", "goal_kind": "weekly_practice", "grade": 8},
        headers=h,
    )
    assert r.json()["grade"] == 8
    a = client.post("/api/v2/assessments", json={"kind": "diagnostic"}, headers=h).json()
    q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
    assert q["skill"]["code"].startswith("7.")  # grade 8 -> start at grade 7
    assert q["selection"]["how"] == "This question helps us find your level."
    assert "grade-7" in q["selection"]["technical"]
    assert client.patch("/api/v2/profile", json={"grade": None}, headers=h).json()["grade"] is None
    assert client.patch("/api/v2/profile", json={"grade": 2}, headers=h).status_code == 422


def test_skill_summary_has_mastery_and_plain_labels(client, math_keys, learner):
    h = learner
    run_assessment(
        client, h, math_keys, {"kind": "skill_check", "skill_id": 129}, lambda i, q: True
    )
    cat = client.get("/api/v2/subject", headers=h).json()
    by = {s["id"]: s for d in cat["domains"] for s in d["skills"]}
    assert by[129]["status_label"] == "Strong" and by[129]["mastery"]["mastered"]
    assert by[129]["mastery"]["progress_hint"] == "Mastered: take the 5-question check"
    assert by[130]["status_label"] == "Not tried yet" and by[130]["review_due"] is False
    page = client.get("/api/v2/skills/129", headers=h).json()
    assert page["next_activity"] == {
        "action": "reassess",
        "label": "Take the short check",
        "skill_id": 129,
    }


# ---------------------------------------------------------------- SQL budget


@pytest.fixture
def count_sql():
    counter = {"n": 0}

    def before(*_args, **_kw):
        counter["n"] += 1

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", before)
    yield counter
    event.remove(engine, "before_cursor_execute", before)


def _fifty_answers(db, user: User) -> None:
    items = db.scalars(select(Item).where(Item.n_skills == 1, Item.exclusion_reason.is_(None)))
    t = datetime.now(UTC) - timedelta(hours=2)
    for k, it in enumerate(list(items)[:50]):
        db.add(
            Interaction(
                user_id=user.id, item_id=it.id, skill_id=it.skill_id, n_skills=1,
                context="practice", practice_id=None, response={"value": "1"},
                is_correct=k % 3 != 0, model_label=k % 3 != 0, created_at=t + timedelta(seconds=k),
            )
        )  # fmt: skip
    e = db.get(Enrollment, (user.id, db.scalar(select(Item.subject_id).limit(1))))
    e.diagnostic_completed_at = t
    db.commit()
    state.refresh(db, user.id)
    recommend.generate(db, user.id, "test")
    db.commit()


def test_home_and_skill_page_stay_within_15_statements(client, math_keys, learner, db, count_sql):
    user = _user(db)
    _fifty_answers(db, user)
    views.home(db, user)  # first visit marks the weekly goal achieved (one UPDATE)
    db.expire_all()
    assert user.full_name  # the request's user is already loaded by auth
    count_sql["n"] = 0
    out = views.home(db, user)
    assert out["next"] is not None
    assert count_sql["n"] <= 15, count_sql["n"]
    db.expire_all()
    assert user.full_name
    count_sql["n"] = 0
    page = views.skill_detail(db, user, 129)
    assert page["attempts"] > 0
    assert count_sql["n"] <= 15, count_sql["n"]


def test_unknown_session_ids_are_404(client, math_keys, learner):
    r = client.get(f"/api/v2/practice/{uuid.uuid4()}/next", headers=learner)
    assert r.status_code == 404


# ---------------------------------------------------------------- review/check dead ends


def _seen_all_but(db, user, skill_id, keep_unseen, when):
    """Record correct single-skill answers for every unseen question of a skill but `keep_unseen`."""
    from app.tutor import engine

    seen = engine.attempted_item_ids(db, user.id)
    fresh = [i for i in db.scalars(engine.usable_items(db, skill_id)) if i.id not in seen]
    for k, it in enumerate(fresh[: len(fresh) - keep_unseen]):
        db.add(
            Interaction(
                user_id=user.id, item_id=it.id, skill_id=skill_id, n_skills=1,
                context="practice", response={"value": "1"}, is_correct=True,
                model_label=True, created_at=when + timedelta(seconds=k),
            )
        )  # fmt: skip
    db.commit()


def test_review_due_with_every_question_seen_still_starts(client, math_keys, learner, db):
    """Review reuses seen questions, and Home offers it only when start_review can serve it."""
    run_assessment(client, learner, math_keys, {"kind": "diagnostic"}, lambda i, q: True)
    user = db.scalar(select(User).where(User.email == "student@example.com"))
    _seen_all_but(db, user, 129, 0, datetime.now(UTC) - timedelta(days=5))
    st = db.get(SkillState, (user.id, 129))
    st.revision_due_at, st.revision_stage = datetime.now(UTC) - timedelta(days=1), 1
    db.commit()
    home = client.get("/api/v2/home", headers=learner).json()
    assert home["next"]["kind"] == "review"
    r = client.post("/api/v2/practice", json={"kind": "review"}, headers=learner)
    assert r.status_code in (200, 201), r.text
    q = client.get(f"/api/v2/practice/{r.json()['id']}/next", headers=learner).json()
    assert q["skill"]["id"] == 129


def test_small_skill_mastered_without_fresh_questions_is_completed(client, math_keys, learner, db):
    """No "Take the short check" that can't start: with < 3 unseen questions left, the mastery
    rule completes the skill, and the check is never offered."""
    run_assessment(client, learner, math_keys, {"kind": "diagnostic"}, lambda i, q: True)
    user = db.scalar(select(User).where(User.email == "student@example.com"))
    _seen_all_but(db, user, 129, 2, datetime.now(UTC) - timedelta(days=1))
    state.refresh(db, user.id, None)
    db.commit()
    page = client.get("/api/v2/skills/129", headers=learner).json()
    assert page["fresh_questions"] == 2 and page["completed"]
    assert page["next_activity"]["action"] != "reassess"
    home = client.get("/api/v2/home", headers=learner).json()
    assert all(a["kind"] != "reassess" for a in [home["next"], *home["up_next"]] if a)
