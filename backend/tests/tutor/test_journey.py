"""The full demo journey through the API: onboarding -> diagnostic -> diagnosis -> dashboard
-> skill page -> resources -> adaptive practice -> reassessment -> logout/login persistence."""

from __future__ import annotations

from tests.conftest import auth, register
from tests.tutor.conftest import answer_body


def run_assessment(client, h, keys, body, correct_fn):
    a = client.post("/api/v2/assessments", json=body, headers=h)
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    last = None
    for i in range(a.json()["total"]):
        q = client.get(f"/api/v2/assessments/{aid}/next", headers=h).json()
        assert "answer_key" not in q and "correct" not in str(q.get("options"))
        last = client.post(
            f"/api/v2/assessments/{aid}/answer",
            json=answer_body(keys, q, correct_fn(i, q)),
            headers=h,
        )
        assert last.status_code == 200, last.text
        assert last.json()["correct_answer"]  # revealed only AFTER answering
    assert last.json()["complete"]
    return aid, last.json()["result"]


def test_full_student_journey(client, math_keys, learner):
    h, keys = learner, math_keys

    sub = client.get("/api/v2/subject", headers=h).json()
    assert sub["subject"]["name"] == "Mathematics" and sub["n_skills"] == 10
    assert sub["model"]["available"] is True

    # diagnostic: answer every question wrong except grade-7 ones
    aid, result = run_assessment(
        client, h, keys, {"kind": "diagnostic"}, lambda i, q: q["skill"]["code"].startswith("7")
    )
    assert result["answered"] == 10

    diag = client.get("/api/v2/diagnosis", headers=h).json()
    statuses = {s["status"] for s in diag["assessed"]}
    assert statuses <= {"potential_weakness", "developing", "likely_strength"}
    for s in diag["assessed"]:
        assert s["attempts"] >= 1 and s["observed_accuracy"] is not None
    assert all(s["status"] == "needs_assessment" for s in diag["model_estimates_for_unassessed"])

    dash = client.get("/api/v2/dashboard", headers=h).json()
    assert dash["diagnostic_completed"] and dash["continue"] is not None
    rec = dash["continue"]
    assert rec["reason"] and rec["skill"]["id"]
    skill_id = rec["skill"]["id"]

    page = client.get(f"/api/v2/skills/{skill_id}", headers=h).json()
    assert page["resources"], "every available skill has at least its standard link"
    before = page["predicted_p"]
    std = next(r for r in page["resources"] if r["kind"] == "standard")
    assert (
        client.post(
            f"/api/v2/resources/{std['id']}/complete", json={"completed": True}, headers=h
        ).status_code
        == 200
    )
    page2 = client.get(f"/api/v2/skills/{skill_id}", headers=h).json()
    assert page2["predicted_p"] == before and page2["attempts"] == page["attempts"], (
        "resources never change estimates"
    )
    assert page2["resources_done"] == 1

    # guided practice with the 2-up / 2-down rule
    p = client.post(
        "/api/v2/practice", json={"skill_id": skill_id, "guided": True}, headers=h
    ).json()
    assert p["mode"] in ("foundation", "guided")
    seen = set()
    levels = []
    for i in range(p["total"]):
        q = client.get(f"/api/v2/practice/{p['id']}/next", headers=h).json()
        assert q["item_id"] not in seen
        seen.add(q["item_id"])
        assert q["selection"]["how"]
        if i == 0:
            hint = client.post(f"/api/v2/practice/{p['id']}/hint", headers=h).json()
            assert hint["text"]
        r = client.post(
            f"/api/v2/practice/{p['id']}/answer", json=answer_body(keys, q, True), headers=h
        )
        assert r.status_code == 200, r.text
        levels.append(r.json()["difficulty_next"])
        if i == 0:
            assert r.json()["hint_used"] is True
            # duplicate submission of the same question is rejected
            dup = client.post(
                f"/api/v2/practice/{p['id']}/answer", json=answer_body(keys, q, True), headers=h
            )
            assert dup.status_code == 409
    assert r.json()["complete"] and r.json()["summary"]["next"]["action"]
    assert "medium" in levels or "hard" in levels, "correct streaks should raise the difficulty"

    # reassessment uses only fresh questions and compares with initial accuracy
    seen_all = {s for s in seen}
    a = client.post(
        "/api/v2/assessments", json={"kind": "reassessment", "skill_id": skill_id}, headers=h
    ).json()
    for _ in range(a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        assert q["item_id"] not in seen_all
        res = client.post(
            f"/api/v2/assessments/{a['id']}/answer", json=answer_body(keys, q, True), headers=h
        ).json()
    out = res["result"]
    assert out["outcome"] == "improved" and out["completed"] is True
    assert out["reassessment_accuracy"] == 1.0 and "initial_accuracy" in out
    assert out["revision_due_at"]

    path = client.get("/api/v2/path", headers=h).json()
    assert any(s["skill"]["id"] == skill_id for s in path["completed"])
    analytics = client.get("/api/v2/analytics", headers=h).json()
    assert analytics["totals"]["questions"] >= 10 + p["total"] + a["total"]
    assert analytics["totals"]["resources_completed"] == 1

    # log out and back in: progress persists
    client.post("/api/v1/auth/logout", headers=h)
    r = client.post(
        "/api/v1/auth/login", json={"email": "student@example.com", "password": "correct horse 1"}
    )
    h2 = auth(r.json()["access_token"])
    again = client.get("/api/v2/dashboard", headers=h2).json()
    assert (
        again["overview"]["skills_assessed"] == dash["overview"]["skills_assessed"]
        or again["overview"]["skills_assessed"] >= 1
    )
    assert client.get(f"/api/v2/skills/{skill_id}", headers=h2).json()["completed"] is True


def test_struggling_student_gets_support_plan(client, math_keys, learner):
    h, keys = learner, math_keys
    skill_id = 217  # 7.EE.B.4a: has a curated prerequisite (6.EE.B.7) in the fixture
    a = client.post(
        "/api/v2/assessments", json={"kind": "skill_check", "skill_id": skill_id}, headers=h
    ).json()
    for _ in range(a["total"]):
        q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
        client.post(
            f"/api/v2/assessments/{a['id']}/answer", json=answer_body(keys, q, False), headers=h
        )
    page = client.get(f"/api/v2/skills/{skill_id}", headers=h).json()
    assert page["status"] == "potential_weakness" and page["mode"] == "foundation"
    assert page["support_plan"]["message"].startswith("Learning takes time")
    assert any(p["code"] == "6.EE.B.7" for p in page["support_plan"]["prerequisites_to_check"])
    assert page["recent_mistakes"] and page["recent_mistakes"][0]["correct_answer"]
    re = client.post(
        "/api/v2/assessments", json={"kind": "reassessment", "skill_id": skill_id}, headers=h
    ).json()
    for _ in range(re["total"]):
        q = client.get(f"/api/v2/assessments/{re['id']}/next", headers=h).json()
        out = client.post(
            f"/api/v2/assessments/{re['id']}/answer", json=answer_body(keys, q, False), headers=h
        ).json()
    assert out["result"]["outcome"] == "not_improved"


def test_answer_validation_and_isolation(client, math_keys, learner):
    h, keys = learner, math_keys
    a = client.post("/api/v2/assessments", json={"kind": "diagnostic"}, headers=h).json()
    q = client.get(f"/api/v2/assessments/{a['id']}/next", headers=h).json()
    k = keys[q["item_id"]]
    if k["type"] == "numeric":
        bad = client.post(
            f"/api/v2/assessments/{a['id']}/answer",
            json={"item_id": q["item_id"], "value": "abc"},
            headers=h,
        )
        assert bad.status_code == 422  # malformed input doesn't use up the question
    wrong_item = client.post(
        f"/api/v2/assessments/{a['id']}/answer", json={"item_id": 1, "value": "1"}, headers=h
    )
    assert wrong_item.status_code == 409
    other = auth(register(client, email="other@example.com"))
    assert client.get(f"/api/v2/assessments/{a['id']}/next", headers=other).status_code in (
        404,
        409,
    )
    assert client.get("/api/v2/admin/overview", headers=h).status_code == 403


def test_onboarding_required_and_topic_goal(client, math_keys):
    h = auth(register(client))
    assert client.get("/api/v2/dashboard", headers=h).status_code == 409
    r = client.post("/api/v2/onboarding", json={"goal_type": "learn_topic"}, headers=h)
    assert r.status_code == 422
    r = client.post(
        "/api/v2/onboarding",
        json={"goal_type": "learn_topic", "focus_skill_id": 198, "goal_kind": "master_skill"},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["focus_skill"]["id"] == 198
    a = client.post(
        "/api/v2/assessments", json={"kind": "skill_check", "skill_id": 198}, headers=h
    ).json()
    assert a["total"] >= 3


def test_admin_content_management(client, math_keys, db):
    from app.db.models import User

    h = auth(register(client, email="admin@example.com"))
    db.query(User).filter(User.email == "admin@example.com").update({"role": "admin"})
    db.commit()
    ov = client.get("/api/v2/admin/overview", headers=h).json()
    assert ov["available_skills"] == 10 and ov["usable_items"] == 240
    assert any(e["reason"] == "multi_skill" for e in ov["exclusions"])
    items = client.get("/api/v2/admin/skills/129/items", headers=h).json()
    target = next(i for i in items if i["exclusion_reason"] is None)
    r = client.patch(
        f"/api/v2/admin/items/{target['id']}", json={"is_active": False}, headers=h
    ).json()
    assert r["skill_items"] == 23
    res = client.post(
        "/api/v2/admin/resources",
        json={
            "skill_id": 129,
            "kind": "notes",
            "title": "Admin notes",
            "content_md": "### Key idea\nText",
        },
        headers=h,
    )
    assert res.status_code == 201
    assert client.post(
        "/api/v2/admin/prerequisites", json={"skill_id": 166, "prerequisite_id": 217}, headers=h
    ).status_code in (201, 422)
    assert (
        client.post(
            "/api/v2/admin/prerequisites", json={"skill_id": 129, "prerequisite_id": 129}, headers=h
        ).status_code
        == 422
    )


def test_seed_is_idempotent(db, tmp_path):
    from app.tutor.seed import seed_math
    from tests.tutor.conftest import make_dataset

    make_dataset(tmp_path / "d")
    first = seed_math(db, tmp_path / "d", tmp_path / "d" / "artifacts")
    second = seed_math(db, tmp_path / "d", tmp_path / "d" / "artifacts")
    assert first == second and first["usable_items"] == 240 and first["available_skills"] == 10
