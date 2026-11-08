"""FR-PATH, FR-REV, FR-KT-04 end to end, on the real model and database."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.models import (
    Concept,
    LearningPath,
    Mastery,
    MasterySnapshot,
    Question,
    User,
)
from app.ml import knowledge, registry
from tests.conftest import auth, register

P = "/api/v1/learning-path?subject=ML"
R = "/api/v1/revision?subject=ML"
S = "/api/v1/sessions"


def _answer_all(client, db, h, sid, correct_every=2):
    i, r = 0, None
    while True:
        q = client.post(f"{S}/{sid}/next", headers=h)
        if q.status_code != 200:
            return r
        q = q.json()
        key = db.get(Question, q["question_id"]).correct_key if i % correct_every == 0 else None
        r = client.post(
            f"{S}/{sid}/answer",
            headers=h,
            json={"question_id": q["question_id"], "selected_key": key},
        ).json()
        i += 1
        if r["session_complete"]:
            return r


def _diagnostic(client, db, h):
    sid = client.post(S, headers=h, json={"subject": "ML", "type": "diagnostic"}).json()["id"]
    _answer_all(client, db, h, sid)


def _concepts(client, h):
    return {c["code"]: c for c in client.get("/api/v1/subjects/ML/concepts", headers=h).json()}


def _set_mastery(db, code, p, peak, snapshot=True):
    user = db.scalar(select(User))
    cid = db.scalar(select(Concept.id).where(Concept.code == code))
    row = db.get(Mastery, (user.id, cid))
    row.p_mastery, row.peak_mastery, row.updated_at = p, peak, datetime.now(UTC)
    if snapshot:
        db.add(MasterySnapshot(user_id=user.id, concept_id=cid, p_mastery=p))
    db.commit()


def test_needs_enrolment(client, seeded):
    h = auth(register(client))
    assert client.get(P, headers=h).json()["error"]["code"] == "not_enrolled"
    assert client.get(R, headers=h).status_code == 409


def test_before_any_practice_only_starting_points_are_recommended(client, student):
    path = client.get(P, headers=student).json()
    concepts = _concepts(client, student)
    assert path["trigger"] == "manual" and path["model_version"] == "ednet-gbm-v1"
    # Nothing is in place yet, so only concepts with no prerequisites can be recommended:
    # as "new", or as "prerequisite" when other concepts build on them (FR-PATH-02).
    assert path["items"] and {i["reason"] for i in path["items"]} <= {"new", "prerequisite"}
    assert all(not concepts[i["concept"]]["prerequisites"] for i in path["items"])
    assert all(i["mastery"] is None for i in path["items"])  # nothing practised yet


def test_path_after_the_diagnostic_obeys_the_rules(client, db, student):
    _diagnostic(client, db, student)
    path = client.get(P, headers=student).json()
    assert path["trigger"] == "diagnostic"
    assert 1 <= len(path["items"]) <= 5
    concepts = _concepts(client, student)
    dependants = {p for c in concepts.values() for p in c["prerequisites"]}
    for item in path["items"]:
        assert item["explanation"] and item["name"] in item["explanation"]
        m = item["mastery_at_generation"]
        assert item["target_difficulty"] == (1 if m < 0.4 else 2 if m < 0.7 else 3)
        if item["reason"] in ("weak", "new"):  # FR-PATH-02
            for pre in concepts[item["concept"]]["prerequisites"]:
                assert concepts[pre]["mastery"] >= 0.6
        if item["reason"] == "prerequisite":
            assert item["concept"] in dependants
    assert [i["position"] for i in path["items"]] == list(range(1, len(path["items"]) + 1))


def test_completed_sessions_regenerate_the_path_and_keep_history(client, db, student):
    _diagnostic(client, db, student)
    sid = client.post(
        S, headers=student, json={"subject": "ML", "type": "practice", "concept": "ml.knn"}
    ).json()["id"]
    done = _answer_all(client, db, student, sid)
    assert done["session_complete"] and done["changes"][0]["concept"] == "ml.knn"
    paths = db.scalars(select(LearningPath).order_by(LearningPath.generated_at)).all()
    assert [p.trigger for p in paths] == ["diagnostic", "session"]  # FR-PATH-04, FR-PATH-05
    assert [p.is_current for p in paths] == [False, True]
    assert client.get(P, headers=student).json()["id"] == str(paths[-1].id)

    regenerated = client.post(P.replace("?", "/regenerate?"), headers=student).json()
    assert regenerated["trigger"] == "manual"
    assert db.scalar(select(func.count()).select_from(LearningPath)) == 3


def test_recommended_practice_draws_from_the_path(client, db, student):
    _diagnostic(client, db, student)
    top = [i["concept"] for i in client.get(P, headers=student).json()["items"][:3]]
    sid = client.post(S, headers=student, json={"subject": "ML", "type": "practice"}).json()["id"]
    q = client.post(f"{S}/{sid}/next", headers=student).json()
    assert q["concept"] in top


def test_revision_queue_path_and_session(client, db, student):
    _diagnostic(client, db, student)
    assert client.get(R, headers=student).json()["due"] == []
    r = client.post(S, headers=student, json={"subject": "ML", "type": "revision"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nothing_due"

    # The student had mastered SVMs (peak 0.92) and it has decayed to 0.41; k-NN less so.
    _set_mastery(db, "ml.svm", 0.41, 0.92)
    _set_mastery(db, "ml.knn", 0.55, 0.83)
    queue = client.get(R, headers=student).json()
    assert [d["concept"] for d in queue["due"]] == ["ml.svm", "ml.knn"]  # biggest drop first
    assert abs(queue["due"][0]["drop"] - 0.51) < 1e-9

    path = client.get(P, headers=student).json()  # due revisions trigger a new path
    assert path["trigger"] == "revision"
    assert [(i["concept"], i["reason"]) for i in path["items"][:2]] == [
        ("ml.svm", "revision"),
        ("ml.knn", "revision"),
    ]

    sid = client.post(S, headers=student, json={"subject": "ML", "type": "revision"}).json()
    assert sid["target"] == 5  # FR-REV-03
    done = _answer_all(client, db, student, sid["id"], correct_every=1)
    concepts = {c["concept"] for c in done["changes"]}
    assert concepts <= {"ml.svm", "ml.knn"}
    svm = next((c for c in done["changes"] if c["concept"] == "ml.svm"), None)
    assert svm is not None and svm["before"] == 0.41  # FR-REV-04
    detail = client.get(f"{S}/{sid['id']}", headers=student).json()
    assert detail["changes"] == done["changes"]


def test_upcoming_revisions_are_projected_with_the_model(client, db, student):
    _diagnostic(client, db, student)
    _set_mastery(db, "ml.svm", 0.85, 0.9)
    queue = client.get(R, headers=student).json()
    assert queue["horizon_days"] == 180
    [svm] = [u for u in queue["upcoming"] if u["concept"] == "ml.svm"]
    # Whatever the answer, it must agree with the model's own projection.
    user = db.scalar(select(User))
    concept = db.scalar(select(Concept).where(Concept.code == "ml.svm"))
    days = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120, 150, 180]
    now = datetime.now(UTC)
    ps = knowledge.concept_mastery_at(
        db,
        registry.get_model(db),
        user.id,
        concept.subject_id,
        [concept],
        [now + timedelta(days=d) for d in days],
    )[concept.id]
    expected = next((d for d, p in zip(days, ps, strict=True) if p < 0.6), None)
    assert svm["due_in_days"] == expected


def test_stale_mastery_is_recomputed_when_read(client, db, student):
    """FR-KT-04: displayed mastery older than 24 h is recomputed with the model."""
    _diagnostic(client, db, student)
    user = db.scalar(select(User))
    cid = db.scalar(select(Concept.id).where(Concept.code == "ml.svm"))
    row = db.get(Mastery, (user.id, cid))
    real = row.p_mastery
    row.p_mastery, row.updated_at = 0.01, datetime.now(UTC) - timedelta(days=2)
    fresh_cid = db.scalar(select(Concept.id).where(Concept.code == "ml.knn"))
    fresh = db.get(Mastery, (user.id, fresh_cid))
    fresh.p_mastery = 0.02  # updated just now: must NOT be recomputed
    db.commit()
    n_snap = db.scalar(select(func.count()).select_from(MasterySnapshot))

    concepts = _concepts(client, student)
    assert abs(concepts["ml.svm"]["mastery"] - real) < 0.01
    assert concepts["ml.knn"]["mastery"] == 0.02
    db.expire_all()
    assert db.get(Mastery, (user.id, cid)).updated_at > datetime.now(UTC) - timedelta(minutes=1)
    assert db.scalar(select(func.count()).select_from(MasterySnapshot)) == n_snap + 1
