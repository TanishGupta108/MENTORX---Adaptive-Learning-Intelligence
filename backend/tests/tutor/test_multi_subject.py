"""Two subjects side by side: Mathematics (synthetic FoundationalASSIST fixture) and a small
synthetic Geography subject (2 skills x 12 map questions). Nothing may leak between them."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Subject
from app.tutor import kt
from app.tutor.models import Item, ItemSkill, Skill, SkillState
from tests.conftest import auth, register

GEO_SKILLS = [(1000101, "GEO.EU.COUNTRY", "Countries of Europe"), (1000102, "GEO.EU.CITY", "Cities of Europe")]  # fmt: skip
PLACES = ["France", "Spain", "Italy", "Poland", "Norway", "Greece"]


def geo_media(locate: bool, k: int) -> dict:
    if locate:
        regions = [
            {
                "label": L,
                "d": f"M{10 * i} 0 L{10 * i + 5} 5 Z",
                "anchor": [10 * i, 2],
                "shape": "area",
            }
            for i, L in enumerate("ABCD")
        ]
    else:
        regions = [{"label": None, "d": f"M{k} 0 L{k + 5} 5 Z", "anchor": [k, 2], "shape": "area"}]
    return {"kind": "map", "map": "europe", "regions": regions}


@pytest.fixture
def geo(db, math_keys, monkeypatch):
    """GEO subject, active, with 2 skills x 12 multiple-choice map items (answer = option "B").
    The GEO model is pointed at the Maths artifacts so GEO predictions exist (ids unknown to it
    map to the model's 'unknown question' slot)."""
    monkeypatch.setattr(get_settings(), "kt_subjects", "GEO=model_artifacts/foundationalassist")
    kt.reset_cache()
    s = Subject(code="GEO", name="Geography: map skills", description="Map skills.")
    db.add(s)
    db.flush()
    item_id = 100_000_000
    for sid, code, name in GEO_SKILLS:
        db.add(
            Skill(
                id=sid, subject_id=s.id, code=code, name=name, description="", grade=None,
                domain_code="EU", domain_name="Europe", n_items=12, is_available=True,
                model_supported=True,
            )
        )  # fmt: skip
        db.flush()
        for k in range(12):
            item_id += 1
            locate = k % 2 == 1
            place = PLACES[k % len(PLACES)]
            body = (
                f"<p>Where is {place}? Choose the letter on the map.</p>"
                if locate
                else "<p>What is the name of the highlighted country?</p>"
            )
            options = [
                {"id": L, "html": L if locate else PLACES[(k + j) % len(PLACES)]}
                for j, L in enumerate("ABCD")
            ]
            db.add(
                Item(
                    id=item_id, subject_id=s.id, skill_id=sid, body_html=body,
                    answer_type="multiple_choice", options=options, answer_key=["B"],
                    difficulty=["easy", "medium", "hard"][k % 3], success_rate=0.6,
                    train_attempts=50, n_skills=1, problem_set="GEO", exclusion_reason=None,
                    is_active=True, media=geo_media(locate, k),
                )
            )  # fmt: skip
            db.add(ItemSkill(item_id=item_id, skill_id=sid))
    db.commit()
    yield s
    kt.reset_cache()


def _answer_check(client, h, skill_id, choice="B", n=None):
    a = client.post(
        "/api/v2/assessments", json={"kind": "skill_check", "skill_id": skill_id}, headers=h
    )
    assert a.status_code == 201, a.text
    a = a.json()
    out = None
    for _ in range(n or a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        out = client.post(
            f"/api/v2/assessments/{a['id']}/answer",
            json={"item_id": q["item_id"], "choice": choice},
            headers=h,
        ).json()
    return a, out


def test_subjects_list_and_switch(client, learner, geo):
    h = learner
    subjects = client.get("/api/v2/subjects", headers=h).json()
    by = {s["code"]: s for s in subjects}
    assert set(by) == {"MATH", "GEO"}
    assert by["MATH"]["current"] and by["MATH"]["enrolled"] and by["MATH"]["grades"]
    assert not by["GEO"]["enrolled"] and not by["GEO"]["grades"] and by["GEO"]["notice"]
    assert "slepemapy" in by["GEO"]["attribution"] and "CC BY-NC 4.0" in by["MATH"]["attribution"]
    assert by["GEO"]["n_skills"] == 2 and by["GEO"]["n_questions"] == 24
    assert client.put("/api/v2/profile/subject", json={"code": "XYZ"}, headers=h).status_code == 404
    p = client.put("/api/v2/profile/subject", json={"code": "GEO"}, headers=h).json()
    assert p["subject_code"] == "GEO" and p["subjects_enrolled"] == ["MATH", "GEO"]
    assert p["diagnostic_completed"] is False
    cat = client.get("/api/v2/subject", headers=h).json()
    assert cat["subject"]["code"] == "GEO" and cat["n_skills"] == 2
    assert cat["subject"]["notice"] and cat["subject"]["attribution"]
    assert {s["code"] for d in cat["domains"] for s in d["skills"]} == {c for _, c, _ in GEO_SKILLS}
    home = client.get("/api/v2/home", headers=h).json()
    assert home["subject"]["code"] == "GEO" and home["next"]["kind"] == "diagnostic"
    assert home["mixed"]["available"] is False
    mixed = client.post("/api/v2/practice", json={"kind": "mixed"}, headers=h)
    assert mixed.status_code == 409
    client.put("/api/v2/profile/subject", json={"code": "MATH"}, headers=h)
    cat = client.get("/api/v2/subject", headers=h).json()
    assert cat["subject"]["code"] == "MATH" and cat["n_skills"] == 10


def test_map_questions_never_leak_the_answer(client, learner, geo):
    h = learner
    client.put("/api/v2/profile/subject", json={"code": "GEO"}, headers=h)
    a = client.post(
        "/api/v2/assessments", json={"kind": "skill_check", "skill_id": 1000101}, headers=h
    ).json()
    for _ in range(a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        text = str(q)
        assert "answer_key" not in q and "'code': 'fr'" not in text
        m = q["media"]
        assert m["kind"] == "map" and m["map"] == "europe"
        assert all(set(r) == {"label", "d", "anchor", "shape"} for r in m["regions"])
        assert len(m["regions"]) in (1, 4)
        r = client.post(
            f"/api/v2/assessments/{a['id']}/answer",
            json={"item_id": q["item_id"], "choice": "B"},
            headers=h,
        ).json()
        assert r["correct"] and r["correct_answer"]["option_ids"] == ["B"]


def test_answers_in_one_subject_never_change_the_other(client, learner, geo, math_keys, db):
    from tests.tutor.test_journey import run_assessment

    h = learner
    user_id = db.scalar(select(SkillState.user_id).limit(1))
    client.put("/api/v2/profile/subject", json={"code": "GEO"}, headers=h)
    _answer_check(client, h, 1000101)
    geo_before = client.get("/api/v2/skills/1000101", headers=h).json()
    assert geo_before["attempts"] == 6 and geo_before["predicted_p"] is not None
    assert geo_before["subject"]["code"] == "GEO" and geo_before["notice"]
    other_before = client.get("/api/v2/skills/1000102", headers=h).json()["predicted_p"]

    client.put("/api/v2/profile/subject", json={"code": "MATH"}, headers=h)
    run_assessment(client, h, math_keys, {"kind": "diagnostic"}, lambda i, q: i % 2 == 0)
    geo_after = client.get("/api/v2/skills/1000101", headers=h).json()
    assert geo_after["attempts"] == geo_before["attempts"]
    assert geo_after["predicted_p"] == pytest.approx(geo_before["predicted_p"])
    assert client.get("/api/v2/skills/1000102", headers=h).json()["predicted_p"] == pytest.approx(
        other_before
    )
    # the Maths model only ever sees Maths answers (and vice versa)
    math_id = db.scalar(select(Subject.id).where(Subject.code == "MATH"))
    hist = kt.history(db, user_id, math_id)
    assert hist and all(a.question_id < 100_000_000 for a in hist)
    assert all(a.question_id > 100_000_000 for a in kt.history(db, user_id, geo.id))
    # Maths diagnosis/catalog contain no Geography skills
    diag = client.get("/api/v2/diagnosis", headers=h).json()
    assert all(not s["code"].startswith("GEO") for s in diag["assessed"])
    analytics = client.get("/api/v2/analytics", headers=h).json()
    assert analytics["totals"]["questions"] == 10  # the 6 GEO answers are not in Maths progress


def test_per_subject_diagnostic_flag_and_shared_streak(client, learner, geo, math_keys):
    from tests.tutor.test_journey import run_assessment

    h = learner
    run_assessment(client, h, math_keys, {"kind": "diagnostic"}, lambda i, q: True)
    assert client.get("/api/v2/profile", headers=h).json()["diagnostic_completed"] is True
    p = client.put("/api/v2/profile/subject", json={"code": "GEO"}, headers=h).json()
    assert p["diagnostic_completed"] is False
    a = client.post("/api/v2/assessments", json={"kind": "diagnostic"}, headers=h).json()
    assert a["subject"]["code"] == "GEO" and a["total"] == 2  # two core GEO skills
    for _ in range(a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        assert q["skill"]["id"] in {s for s, _, _ in GEO_SKILLS}
        client.post(
            f"/api/v2/assessments/{a['id']}/answer",
            json={"item_id": q["item_id"], "choice": "B"},
            headers=h,
        )
    by = {s["code"]: s for s in client.get("/api/v2/subjects", headers=h).json()}
    assert by["GEO"]["diagnostic_completed"] and by["MATH"]["diagnostic_completed"]
    home = client.get("/api/v2/home", headers=h).json()
    assert home["streak"]["today"] == 12  # 10 Maths + 2 Geography answers, one shared streak
    assert home["streak"]["current"] == 1


def test_seeding_maths_keeps_geography(db, geo, tmp_path):
    from app.tutor.seed import seed_math
    from tests.tutor.conftest import make_dataset

    ml = Subject(code="ML", name="Machine learning", description="v1 demo")
    db.add(ml)
    db.commit()
    make_dataset(tmp_path / "again")
    seed_math(db, tmp_path / "again", tmp_path / "again" / "artifacts")
    db.expire_all()
    assert db.get(Subject, geo.id).is_active
    assert not db.scalar(select(Subject).where(Subject.code == "ML")).is_active
    geo_items = db.scalars(select(Item).where(Item.subject_id == geo.id)).all()
    assert len(geo_items) == 24 and all(i.media for i in geo_items)
    assert db.scalar(select(ItemSkill).where(ItemSkill.item_id == geo_items[0].id)) is not None
    assert db.get(Skill, 1000101).is_available and db.get(Skill, 1000101).n_items == 12


def test_onboarding_into_another_subject(client, geo):
    h = auth(register(client, email="geo@example.com"))
    r = client.post(
        "/api/v2/onboarding",
        json={
            "goal_type": "assess_overall",
            "goal_kind": "weekly_practice",
            "subject_code": "GEO",
            "pace_preference": "challenge",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["subject_code"] == "GEO" and p["pace_preference"] == "challenge" and p["grade"] is None
    bad = client.post(
        "/api/v2/onboarding",
        json={"goal_type": "assess_overall", "grade": 12},
        headers=h,
    )
    assert bad.status_code == 422


def test_profile_edit_follows_the_onboarding_rules(client, learner, geo, math_keys):
    """PATCH /profile: a focus topic must be an available skill of the current subject, and
    "learn a topic" needs one (it used to answer 500 for an unknown id and accept the rest)."""
    h = learner
    geo_skill = GEO_SKILLS[0][0]
    for body in (
        {"focus_skill_id": 99_999_999},  # no such skill
        {"focus_skill_id": geo_skill},  # another subject's skill
        {"goal_type": "learn_topic"},  # no topic chosen
        {"goal_type": "learn_topic", "focus_skill_id": None},
    ):
        r = client.patch("/api/v2/profile", json=body, headers=h)
        assert r.status_code == 422, (body, r.status_code, r.text)
    ok = client.patch(
        "/api/v2/profile", json={"goal_type": "learn_topic", "focus_skill_id": 129}, headers=h
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["goal_type"] == "learn_topic"
    cleared = client.patch("/api/v2/profile", json={"focus_skill_id": None}, headers=h)
    assert cleared.status_code == 422  # still learning a topic, so it can't be removed alone
