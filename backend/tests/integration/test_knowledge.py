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
