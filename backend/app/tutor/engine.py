"""Shared question serving and answer recording for assessments and practice.

Guarantees (kept from the v1 quiz engine):
- answer keys never leave the server before the student has answered;
- the server remembers which item it served, so an answer is accepted only for that item,
  exactly once (the session row is locked and the interaction has a unique constraint);
- the model's prediction is stored BEFORE the answer, for honest live evaluation;
- a malformed answer (e.g. "abc" for a numeric question) is rejected without using up the item.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.tutor import answers
from app.tutor.models import Interaction, Item, Skill


def now() -> datetime:
    return datetime.now(UTC)


def public_item(
    db: Session, item: Item, position: int | None = None, total: int | None = None
) -> dict:
    """Everything the client needs to render a question, and nothing that reveals the answer."""
    skill = db.get(Skill, item.skill_id)
    return {
        "item_id": item.id,
        "skill": {"id": skill.id, "code": skill.code, "name": skill.name},
        "body_html": item.body_html,
        "answer_type": item.answer_type,
        "options": [{"id": o["id"], "html": o["html"]} for o in item.options],
        "difficulty": item.difficulty,
        "position": position,
        "total": total,
    }


def usable_items(db: Session, skill_id: int | None = None):
    stmt = select(Item).where(Item.is_active, Item.exclusion_reason.is_(None))
    if skill_id is not None:
        stmt = stmt.where(Item.skill_id == skill_id)
    return stmt


def attempted_item_ids(db: Session, user_id: uuid.UUID) -> set[int]:
    return set(db.scalars(select(Interaction.item_id).where(Interaction.user_id == user_id)))


def record(
    db: Session,
    user_id: uuid.UUID,
    item: Item,
    response: dict,
    *,
    context: str,
    served_at: datetime | None,
    predicted_p: float | None,
    assessment_id: uuid.UUID | None = None,
    practice_id: uuid.UUID | None = None,
    hint_used: bool = False,
    saw_answer: bool = False,
) -> Interaction:
    if saw_answer:
        is_correct = False
    else:
        try:
            is_correct = answers.check(item.answer_type, item.answer_key, response)
        except ValueError as exc:
            raise AppError(422, "invalid_answer", str(exc)) from exc
    t = now()
    inter = Interaction(
        user_id=user_id,
        item_id=item.id,
        skill_id=item.skill_id,
        context=context,
        assessment_id=assessment_id,
        practice_id=practice_id,
        response=response if not saw_answer else {"revealed": True},
        is_correct=is_correct,
        hint_used=hint_used,
        saw_answer=saw_answer,
        model_label=is_correct and not hint_used and not saw_answer,
        response_ms=int((t - served_at).total_seconds() * 1000) if served_at else None,
        predicted_p=predicted_p,
        difficulty=item.difficulty,
        created_at=t,
    )
    db.add(inter)
    try:
        db.flush()
    except IntegrityError as exc:  # same item answered twice in one session
        db.rollback()
        raise AppError(409, "already_answered", "This question has already been answered.") from exc
    return inter


def reveal(item: Item) -> dict:
    return answers.describe_key(item.answer_type, item.answer_key, item.options)


def skill_accuracy(db: Session, user_id: uuid.UUID, skill_id: int) -> tuple[int, int]:
    n, c = db.execute(
        select(func.count(), func.count().filter(Interaction.is_correct)).where(
            Interaction.user_id == user_id, Interaction.skill_id == skill_id
        )
    ).one()
    return int(c), int(n)
