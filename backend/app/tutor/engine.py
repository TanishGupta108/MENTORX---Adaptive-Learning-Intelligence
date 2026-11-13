"""Shared question serving and answer recording for assessments and practice.

Guarantees (kept from the v1 quiz engine):
- answer keys never leave the server before the student has answered;
- the server remembers which item it served, so an answer is accepted only for that item,
  exactly once (the session row is locked and the interaction has a unique constraint);
- the model's prediction is stored BEFORE the answer, for honest live evaluation;
- a malformed answer (e.g. "abc" for a numeric question) is rejected without using up the item;
- the question id the client sees is opaque for subjects whose ids encode the answer
  (Geography ids contain the Slepemapy place id): see `public_id`.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Subject
from app.tutor import answers
from app.tutor.models import Interaction, Item, ItemSkill, Skill
from app.tutor.subjects import meta as subject_meta


def now() -> datetime:
    return datetime.now(UTC)


def item_skills(db: Session, item_ids) -> dict[int, list[int]]:
    """All skills of each given question (the dataset's full mapping)."""
    out: dict[int, list[int]] = {}
    if not item_ids:
        return out
    for iid, sid in db.execute(
        select(ItemSkill.item_id, ItemSkill.skill_id).where(ItemSkill.item_id.in_(list(item_ids)))
    ):
        out.setdefault(iid, []).append(sid)
    return {k: sorted(v) for k, v in out.items()}


def public_id(db: Session, item: Item) -> int:
    """The question id sent to the client. Mathematics: the dataset problem id. Subjects with
    `opaque_ids` (Geography, whose ids contain the place id that public data maps to the
    answer): a keyed hash of the id, stable for this server and meaningless without its secret.
    Answers are matched against the question the server served, so it is never reversed."""
    subject = db.get(Subject, item.subject_id)
    if not subject_meta(subject.code if subject else None).get("opaque_ids"):
        return item.id
    key = hashlib.sha256(f"item-id:{get_settings().jwt_secret}".encode()).digest()
    digest = hmac.new(key, str(item.id).encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:4], "big") % 2_000_000_000 + 1


def is_current(db: Session, current_item_id: int | None, submitted: int) -> bool:
    """True if `submitted` (a public id) names the question currently being shown."""
    if current_item_id is None:
        return False
    return public_id(db, db.get(Item, current_item_id)) == submitted


def public_item(
    db: Session, item: Item, position: int | None = None, total: int | None = None
) -> dict:
    """Everything the client needs to render a question, and nothing that reveals the answer."""
    skill = db.get(Skill, item.skill_id)
    skills = [skill]
    if item.n_skills > 1:
        ids = item_skills(db, [item.id]).get(item.id, [item.skill_id])
        skills = [db.get(Skill, i) for i in ids]
    return {
        "item_id": public_id(db, item),
        "skill": {"id": skill.id, "code": skill.code, "name": skill.name},
        "skills": [{"id": s.id, "code": s.code, "name": s.name} for s in skills if s],
        "mixed": item.n_skills > 1,
        "body_html": item.body_html,
        "answer_type": item.answer_type,
        "input_hint": answers.INPUT_HINTS.get(item.answer_type),
        "options": [{"id": o["id"], "html": o["html"]} for o in item.options],
        "difficulty": item.difficulty,
        "media": public_media(item),
        "position": position,
        "total": total,
    }


def public_media(item: Item) -> dict | None:
    """Map media for the client: geometry and letters only (never place codes or the key)."""
    m = item.media
    if not isinstance(m, dict) or m.get("kind") != "map":
        return None
    return {
        "kind": "map",
        "map": m.get("map"),
        "regions": [
            {
                "label": r.get("label"),
                "d": r.get("d"),
                "anchor": r.get("anchor"),
                "shape": r.get("shape", "area"),
            }
            for r in m.get("regions", [])
        ],
    }


def usable_items(
    db: Session, skill_id: int | None = None, mixed: bool = False, subject_id: int | None = None
):
    """Servable questions. With a skill: that skill's SINGLE-skill questions (multi-skill
    questions are only used in Mixed practice). mixed=True: multi-skill questions only.
    `subject_id` limits the pool to one subject (needed whenever no skill is given)."""
    stmt = select(Item).where(Item.is_active, Item.exclusion_reason.is_(None))
    if subject_id is not None:
        stmt = stmt.where(Item.subject_id == subject_id)
    if mixed:
        return stmt.where(Item.n_skills > 1)
    stmt = stmt.where(Item.n_skills == 1)
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
            is_correct = answers.check(item.answer_type, item.answer_key, response, item.body_html)
        except ValueError as exc:
            raise AppError(422, "invalid_answer", str(exc)) from exc
    t = now()
    inter = Interaction(
        user_id=user_id,
        item_id=item.id,
        skill_id=item.skill_id,
        n_skills=item.n_skills,
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
    """(correct, answered) on the skill's own single-skill questions."""
    n, c = db.execute(
        select(func.count(), func.count().filter(Interaction.is_correct)).where(
            Interaction.user_id == user_id,
            Interaction.skill_id == skill_id,
            Interaction.n_skills == 1,
        )
    ).one()
    return int(c), int(n)
