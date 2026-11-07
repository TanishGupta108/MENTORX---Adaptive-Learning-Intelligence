"""Store mastery estimates and their history (FR-KT-03)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Attempt, Concept, Mastery, MasterySnapshot, Question
from app.ml import knowledge
from app.ml.registry import LoadedModel


def _attempt_counts(db: Session, user_id: uuid.UUID, concept_ids: list[int]) -> dict[int, tuple]:
    return {
        cid: (int(n), last)
        for cid, n, last in db.execute(
            select(Question.concept_id, func.count(), func.max(Attempt.created_at))
            .join(Attempt, Attempt.question_id == Question.id)
            .where(Attempt.user_id == user_id, Question.concept_id.in_(concept_ids))
            .group_by(Question.concept_id)
        )
    }


def recompute(
    db: Session,
    model: LoadedModel,
    user_id: uuid.UUID,
    subject_id: int,
    concepts: list[Concept],
    now: datetime,
    attempt_id: int | None = None,
) -> dict[int, tuple[float | None, float]]:
    """Recompute and store mastery for `concepts`. Returns {concept_id: (before, after)}."""
    if not concepts:
        return {}
    ids = [c.id for c in concepts]
    before = {
        m.concept_id: m.p_mastery
        for m in db.scalars(
            select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id.in_(ids))
        )
    }
    after = knowledge.concept_mastery(db, model, user_id, subject_id, concepts, now)
    counts = _attempt_counts(db, user_id, ids)
    for cid, p in after.items():
        n, last = counts.get(cid, (0, None))
        stmt = insert(Mastery).values(
            user_id=user_id,
            concept_id=cid,
            p_mastery=p,
            peak_mastery=p,
            n_attempts=n,
            last_attempt_at=last,
            model_version_id=model.version_id,
            updated_at=now,
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "concept_id"],
                set_={
                    "p_mastery": p,
                    # peak only counts once the student has actually practised (revision rule)
                    "peak_mastery": func.greatest(Mastery.peak_mastery, p) if n else p,
                    "n_attempts": n,
                    "last_attempt_at": last,
                    "model_version_id": model.version_id,
                    "updated_at": now,
                },
            )
        )
        db.add(MasterySnapshot(user_id=user_id, concept_id=cid, p_mastery=p, attempt_id=attempt_id))
    return {cid: (before.get(cid), p) for cid, p in after.items()}
