"""The real model behaves as the product needs: fallbacks work, mastery decays with time."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import Concept, ModelVersion, Subject, User
from app.ml import knowledge, registry
from app.services import mastery


def test_bundled_models_are_registered_and_primary_is_active(db, seeded):
    model = registry.get_model(db)
    assert model.is_ml and model.model_type == "gbm" and model.use_time
    names = {m.name: m for m in db.scalars(select(ModelVersion))}
    assert {"ednet-gbm-v1", "ednet-logreg-v1", "ednet-prior-v1"} <= set(names)
    assert names["ednet-gbm-v1"].is_active


def test_corrupted_primary_falls_back_to_logistic_regression(db, seeded, monkeypatch):
    real = registry.load_manifest

    def tampered():
        m = real()
        m["models"][0]["sha256"] = "0" * 64  # primary no longer matches its file
        return m

    monkeypatch.setattr(registry, "load_manifest", tampered)
    model = registry.get_model(db)
    assert model.model_type == "logreg" and model.is_ml


def test_all_models_broken_falls_back_to_constant_prior(db, seeded, monkeypatch):
    real = registry.load_manifest

    def broken():
        m = real()
        for e in m["models"]:
            e["sha256"] = "0" * 64
        return m

    monkeypatch.setattr(registry, "load_manifest", broken)
    model = registry.get_model(db)
    assert model.model_type == "prior" and not model.is_ml
    assert model.predict([{}, {}]).tolist() == [
        pytest.approx(m := real()["prior"]["p"]),
        pytest.approx(m),
    ]


def _student_with_history(db, client, correct_answers: int):
    from tests.conftest import auth, register

    h = auth(register(client))
    client.post("/api/v1/subjects/ML/enroll", headers=h)
    sid = client.post(
        "/api/v1/sessions",
        headers=h,
        json={"subject": "ML", "type": "practice", "concept": "ml.svm"},
    ).json()["id"]
    from app.db.models import Question

    for _ in range(correct_answers):
        q = client.post(f"/api/v1/sessions/{sid}/next", headers=h).json()
        key = db.get(Question, q["question_id"]).correct_key
        client.post(
            f"/api/v1/sessions/{sid}/answer",
            headers=h,
            json={"question_id": q["question_id"], "selected_key": key},
        )
    return db.scalar(select(User))


def test_mastery_decays_when_a_concept_is_not_practised(db, client, seeded):
    """Design decision D-6: the revision scheduler relies on this."""
    user = _student_with_history(db, client, correct_answers=5)
    subject = db.scalar(select(Subject))
    svm = db.scalar(select(Concept).where(Concept.code == "ml.svm"))
    model = registry.get_model(db)
    now = datetime.now(UTC)
    p_now = knowledge.concept_mastery(
        db, model, user.id, subject.id, [svm], now + timedelta(hours=1)
    )
    p_later = knowledge.concept_mastery(
        db, model, user.id, subject.id, [svm], now + timedelta(days=180)
    )
    assert p_later[svm.id] < p_now[svm.id]


def test_peak_mastery_never_decreases(db, client, seeded):
    user = _student_with_history(db, client, correct_answers=4)
    subject = db.scalar(select(Subject))
    svm = db.scalar(select(Concept).where(Concept.code == "ml.svm"))
    model = registry.get_model(db)
    from app.db.models import Mastery

    peak_before = db.get(Mastery, (user.id, svm.id)).peak_mastery
    mastery.recompute(
        db, model, user.id, subject.id, [svm], datetime.now(UTC) + timedelta(days=365)
    )
    db.commit()
    row = db.get(Mastery, (user.id, svm.id))
    db.refresh(row)
    assert row.p_mastery < peak_before and row.peak_mastery == pytest.approx(peak_before)


def test_mastery_never_rises_with_time_alone(db, client, seeded):
    """Without new answers, projected mastery is non-increasing (revision can't flicker)."""
    user = _student_with_history(db, client, correct_answers=6)
    subject = db.scalar(select(Subject))
    concepts = db.scalars(select(Concept)).all()
    model = registry.get_model(db)
    now = datetime.now(UTC)
    times = [now + timedelta(days=d) for d in (0, 0.5, 1, 4, 9, 20, 33, 70, 100, 200, 400, 800)]
    at = knowledge.concept_mastery_at(db, model, user.id, subject.id, concepts, times)
    assert len(at) == len(concepts)
    for ps in at.values():
        assert all(b <= a for a, b in zip(ps, ps[1:], strict=False))


def _answer_some(client, db, h, concept, n, correct):
    from app.db.models import Question

    sid = client.post(
        "/api/v1/sessions",
        headers=h,
        json={"subject": "ML", "type": "practice", "concept": concept},
    ).json()["id"]
    for _ in range(n):
        q = client.post(f"/api/v1/sessions/{sid}/next", headers=h).json()
        key = db.get(Question, q["question_id"]).correct_key if correct else None
        client.post(
            f"/api/v1/sessions/{sid}/answer",
            headers=h,
            json={"question_id": q["question_id"], "selected_key": key},
        )


def test_cached_difficulty_matches_a_fresh_computation(db, client, seeded, monkeypatch):
    """The answer-statistics cache (M12 performance fix) never changes the numbers it serves
    for a given snapshot, and never counts the requesting student's own answers."""
    from app.core.config import get_settings
    from app.db.models import Question
    from tests.conftest import auth, register

    a = auth(register(client, email="a@example.com"))
    b = auth(register(client, email="b@example.com"))
    for h in (a, b):
        client.post("/api/v1/subjects/ML/enroll", headers=h)
    _answer_some(client, db, a, "ml.knn", 5, correct=True)
    _answer_some(client, db, b, "ml.knn", 5, correct=False)

    questions = list(db.scalars(select(Question).join(Concept).where(Concept.code == "ml.knn")))
    user_a = db.scalar(select(User).where(User.email == "a@example.com"))

    knowledge.reset_stats_cache()
    cached = knowledge.difficulty(db, questions, user_a.id)
    # The student's own new answers after the snapshot must not leak into "other students".
    _answer_some(client, db, a, "ml.knn", 3, correct=True)
    assert knowledge.difficulty(db, questions, user_a.id) == cached

    monkeypatch.setattr(get_settings(), "difficulty_cache_seconds", 0)  # always fresh
    assert knowledge.difficulty(db, questions, user_a.id) == cached  # only b counts for a

    # Another student's new answers appear once the cache is refreshed.
    monkeypatch.setattr(get_settings(), "difficulty_cache_seconds", 60)
    knowledge.reset_stats_cache()
    before = knowledge.difficulty(db, questions, user_a.id)
    _answer_some(client, db, b, "ml.knn", 4, correct=False)
    assert knowledge.difficulty(db, questions, user_a.id) == before  # within the TTL
    knowledge.reset_stats_cache()
    after = knowledge.difficulty(db, questions, user_a.id)
    knn = questions[0].concept_id
    assert after[1][knn].concept_logit < before[1][knn].concept_logit  # b's wrong answers count
