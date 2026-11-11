"""Learning resources, completions and hints.

Opening or completing a resource NEVER changes a skill estimate: only answers do.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import User
from app.tutor.models import Resource, ResourceCompletion, Skill

KIND_ORDER = {
    "notes": 0,
    "worked_example": 1,
    "video": 2,
    "article": 3,
    "practice_tip": 4,
    "standard": 5,
}
GENERIC_HINT = (
    "Read the question again and underline what is given and what is asked. "
    "Estimate the answer first, then check that your final answer is close to the estimate "
    "and has the right units."
)


def out(r: Resource, done: set[int], skill: Skill | None = None) -> dict:
    return {
        "id": r.id,
        "skill_id": r.skill_id,
        "skill_name": skill.name if skill else None,
        "skill_code": skill.code if skill else None,
        "kind": r.kind,
        "title": r.title,
        "description": r.description,
        "url": r.url,
        "content_md": r.content_md,
        "minutes": r.minutes,
        "source_label": r.source_label,
        "is_original": r.is_original,
        "completed": r.id in done,
    }


def completed_ids(db: Session, user: User) -> set[int]:
    return set(
        db.scalars(
            select(ResourceCompletion.resource_id).where(ResourceCompletion.user_id == user.id)
        )
    )


def for_skill(db: Session, user: User, skill_id: int) -> list[dict]:
    done = completed_ids(db, user)
    rows = db.scalars(select(Resource).where(Resource.skill_id == skill_id, Resource.is_active))
    return [
        out(r, done)
        for r in sorted(rows, key=lambda r: (KIND_ORDER.get(r.kind, 9), r.position, r.id))
    ]


def library(db: Session, user: User, kind: str | None = None, q: str | None = None) -> list[dict]:
    done = completed_ids(db, user)
    stmt = (
        select(Resource, Skill)
        .join(Skill, Skill.id == Resource.skill_id)
        .where(Resource.is_active, Skill.is_available)
    )
    if kind:
        stmt = stmt.where(Resource.kind == kind)
    else:
        stmt = stmt.where(Resource.kind != "standard")  # standards are listed on each skill page
    if q:
        like = f"%{q.strip()[:60]}%"
        stmt = stmt.where(
            Resource.title.ilike(like) | Skill.name.ilike(like) | Skill.code.ilike(like)
        )
    rows = db.execute(stmt.order_by(Skill.grade, Skill.code, Resource.position)).all()
    return [out(r, done, s) for r, s in rows]


def set_completed(db: Session, user: User, resource_id: int, completed: bool) -> dict:
    r = db.get(Resource, resource_id)
    if r is None or not r.is_active:
        raise AppError(404, "resource_not_found", "Resource not found.")
    row = db.get(ResourceCompletion, (user.id, resource_id))
    if completed and row is None:
        db.add(ResourceCompletion(user_id=user.id, resource_id=resource_id))
    elif not completed and row is not None:
        db.delete(row)
    db.commit()
    return {"id": resource_id, "completed": completed}


def hint_for(db: Session, skill_id: int) -> dict:
    """A concept reminder from the skill's notes ("Key idea"), else a general strategy tip.
    The dataset has no per-question hints, so hints are about the skill, never the answer."""
    notes = db.scalar(
        select(Resource)
        .where(Resource.skill_id == skill_id, Resource.kind == "notes", Resource.is_active)
        .limit(1)
    )
    if notes and notes.content_md:
        m = re.search(r"###\s*Key idea\s*\n(.+?)(\n###|\Z)", notes.content_md, re.S)
        text = (m.group(1) if m else notes.content_md.split("\n\n")[0]).strip()
        return {"kind": "concept", "text": text, "source": notes.title}
    return {"kind": "strategy", "text": GENERIC_HINT, "source": "General problem-solving tip"}
