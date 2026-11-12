"""Simple content management: resources, skill descriptions, question availability and
curated prerequisites. Admins are users with role 'admin' or listed in ADMIN_EMAILS."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import User
from app.tutor import kt
from app.tutor import resources as res_service
from app.tutor.html import plain_text
from app.tutor.models import Interaction, Item, Resource, Skill, SkillPrerequisite
from app.tutor.profile import is_admin
from app.tutor.seed import MIN_ITEMS_FOR_SKILL


def require_admin(user: User) -> None:
    if not is_admin(user):
        raise AppError(403, "forbidden", "Admins only.")


def overview(db: Session) -> dict:
    reasons = db.execute(
        select(Item.exclusion_reason, func.count())
        .group_by(Item.exclusion_reason)
        .order_by(func.count().desc())
    ).all()
    return {
        "skills": db.scalar(select(func.count()).select_from(Skill)),
        "available_skills": db.scalar(
            select(func.count()).select_from(Skill).where(Skill.is_available)
        ),
        "items": db.scalar(select(func.count()).select_from(Item)),
        "usable_items": db.scalar(
            select(func.count())
            .select_from(Item)
            .where(Item.is_active, Item.exclusion_reason.is_(None))
        ),
        "usable_mixed_items": db.scalar(
            select(func.count())
            .select_from(Item)
            .where(Item.is_active, Item.exclusion_reason.is_(None), Item.n_skills > 1)
        ),
        "disabled_by_admin": db.scalar(
            select(func.count()).select_from(Item).where(~Item.is_active)
        ),
        "exclusions": [{"reason": r or "usable", "count": n} for r, n in reasons],
        "resources": db.scalar(select(func.count()).select_from(Resource)),
        "prerequisites": db.scalar(select(func.count()).select_from(SkillPrerequisite)),
    }


def skills(db: Session, q: str | None) -> list[dict]:
    stmt = select(Skill).order_by(Skill.grade, Skill.code, Skill.id)
    if q:
        like = f"%{q.strip()[:60]}%"
        stmt = stmt.where(Skill.name.ilike(like) | Skill.code.ilike(like))
    return [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "description": s.description,
            "domain_name": s.domain_name,
            "n_items": s.n_items,
            "is_available": s.is_available,
        }
        for s in db.scalars(stmt)
    ]


def update_skill(db: Session, skill_id: int, description: str) -> dict:
    s = db.get(Skill, skill_id)
    if s is None:
        raise AppError(404, "skill_not_found", "Skill not found.")
    s.description = description.strip()
    db.commit()
    return {"id": s.id, "description": s.description}


def items(db: Session, skill_id: int) -> list[dict]:
    rows = db.scalars(
        select(Item)
        .where(Item.skill_id == skill_id)
        .order_by(Item.exclusion_reason.nulls_first(), Item.id)
    )
    return [
        {
            "id": i.id,
            "preview": plain_text(i.body_html)[:160],
            "answer_type": i.answer_type,
            "difficulty": i.difficulty,
            "success_rate": i.success_rate,
            "train_attempts": i.train_attempts,
            "exclusion_reason": i.exclusion_reason,
            "n_skills": i.n_skills,
            "is_active": i.is_active,
        }
        for i in rows
    ]


def set_item_active(db: Session, item_id: int, active: bool) -> dict:
    i = db.get(Item, item_id)
    if i is None:
        raise AppError(404, "item_not_found", "Question not found.")
    i.is_active = active
    db.flush()
    s = db.get(Skill, i.skill_id)
    s.n_items = db.scalar(
        select(func.count())
        .select_from(Item)
        .where(
            Item.skill_id == s.id,
            Item.n_skills == 1,
            Item.is_active,
            Item.exclusion_reason.is_(None),
        )
    )
    s.is_available = s.n_items >= MIN_ITEMS_FOR_SKILL and s.model_supported
    db.commit()
    return {
        "id": i.id,
        "is_active": i.is_active,
        "skill_available": s.is_available,
        "skill_items": s.n_items,
    }


def list_resources(db: Session, skill_id: int | None) -> list[dict]:
    stmt = select(Resource).order_by(Resource.skill_id, Resource.position, Resource.id)
    if skill_id:
        stmt = stmt.where(Resource.skill_id == skill_id)
    return [res_service.out(r, set()) | {"is_active": r.is_active} for r in db.scalars(stmt)]


def save_resource(db: Session, data: dict, resource_id: int | None = None) -> dict:
    r = db.get(Resource, resource_id) if resource_id else Resource(is_original=False)
    if r is None:
        raise AppError(404, "resource_not_found", "Resource not found.")
    if data.get("skill_id") is not None and db.get(Skill, data["skill_id"]) is None:
        raise AppError(422, "validation_error", "Unknown skill.")
    for k, v in data.items():
        setattr(r, k, v)
    if not r.url and not r.content_md:
        raise AppError(422, "validation_error", "A resource needs a URL or written content.")
    db.add(r)
    db.commit()
    return res_service.out(r, set()) | {"is_active": r.is_active}


def delete_resource(db: Session, resource_id: int) -> None:
    r = db.get(Resource, resource_id)
    if r is None:
        raise AppError(404, "resource_not_found", "Resource not found.")
    db.delete(r)
    db.commit()


def prerequisites(db: Session) -> list[dict]:
    rows = db.execute(select(SkillPrerequisite)).scalars().all()
    names = {s.id: (s.code, s.name) for s in db.scalars(select(Skill))}
    return [
        {
            "skill_id": p.skill_id,
            "skill": f"{names[p.skill_id][0]} {names[p.skill_id][1]}",
            "prerequisite_id": p.prerequisite_id,
            "prerequisite": f"{names[p.prerequisite_id][0]} {names[p.prerequisite_id][1]}",
            "source": p.source,
        }
        for p in sorted(rows, key=lambda p: (names[p.skill_id][0], p.skill_id))
    ]


def _creates_cycle(db: Session, skill_id: int, prereq_id: int) -> bool:
    """Would skill -> prereq close a loop (prereq already depends on skill)?"""
    edges: dict[int, list[int]] = {}
    for p in db.scalars(select(SkillPrerequisite)):
        edges.setdefault(p.skill_id, []).append(p.prerequisite_id)
    stack, seen = [prereq_id], set()
    while stack:
        cur = stack.pop()
        if cur == skill_id:
            return True
        if cur not in seen:
            seen.add(cur)
            stack.extend(edges.get(cur, []))
    return False


def add_prerequisite(db: Session, skill_id: int, prereq_id: int, user: User) -> dict:
    if skill_id == prereq_id or db.get(Skill, skill_id) is None or db.get(Skill, prereq_id) is None:
        raise AppError(422, "validation_error", "Choose two different, existing skills.")
    if db.get(SkillPrerequisite, (skill_id, prereq_id)):
        raise AppError(409, "exists", "That link already exists.")
    if _creates_cycle(db, skill_id, prereq_id):
        raise AppError(422, "cycle", "That link would create a circular prerequisite chain.")
    db.add(
        SkillPrerequisite(
            skill_id=skill_id,
            prerequisite_id=prereq_id,
            source=f"Curated by admin {user.email}"[:200],
        )
    )
    db.commit()
    return {"skill_id": skill_id, "prerequisite_id": prereq_id}


def remove_prerequisite(db: Session, skill_id: int, prereq_id: int) -> None:
    p = db.get(SkillPrerequisite, (skill_id, prereq_id))
    if p is None:
        raise AppError(404, "not_found", "Link not found.")
    db.delete(p)
    db.commit()


# ---------------------------------------------------------------- live model monitoring

MIN_FOR_METRICS = 20


def _metrics(p: np.ndarray, y: np.ndarray) -> dict:
    out: dict = {
        "n": int(len(y)),
        "observed_rate": float(y.mean()) if len(y) else None,
        "mean_predicted": float(p.mean()) if len(p) else None,
        "auc": None,
        "log_loss": None,
        "brier": None,
        "accuracy": None,
    }
    if len(y) >= MIN_FOR_METRICS:
        pc = np.clip(p, 1e-6, 1 - 1e-6)
        out["log_loss"] = float(log_loss(y, pc, labels=[0, 1]))
        out["brier"] = float(brier_score_loss(y, p))
        out["accuracy"] = float(((p >= 0.5) == (y == 1)).mean())
        if 0 < y.sum() < len(y):
            out["auc"] = float(roc_auc_score(y, p))
    return out


def model_monitor(db: Session) -> dict:
    """How well the served model predicts REAL students' answers in this app.

    Every prediction is stored before the answer is seen, so this is an honest out-of-sample
    check. The label is the model's own target (correct first time, no hint, answer not
    shown). Caveat shown in the UI: practice deliberately serves questions near a target
    success rate, which narrows the spread of predictions and usually lowers AUC compared
    with the offline test set.
    """
    rows = db.execute(
        select(
            Interaction.predicted_p,
            Interaction.model_label,
            Interaction.context,
            Interaction.n_skills,
        ).where(Interaction.predicted_p.is_not(None))
    ).all()
    info = kt.info()
    if not rows:
        return {
            "model": info.__dict__,
            "overall": _metrics(np.array([]), np.array([])),
            "by_context": {},
            "calibration": [],
            "min_for_metrics": MIN_FOR_METRICS,
        }
    p = np.array([r[0] for r in rows], dtype=float)
    y = np.array([int(r[1]) for r in rows], dtype=int)
    ctx = np.array([r[2] for r in rows])
    mixed = np.array([r[3] > 1 for r in rows])
    by_context = {c: _metrics(p[ctx == c], y[ctx == c]) for c in ("assessment", "practice")}
    by_context["mixed_questions"] = _metrics(p[mixed], y[mixed])
    bins = np.linspace(0, 1, 11)
    calibration = []
    for lo, hi in zip(bins[:-1], bins[1:], strict=True):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum():
            calibration.append(
                {
                    "bin": f"{int(lo * 100)}-{int(hi * 100)}%",
                    "mean_predicted": float(p[m].mean()),
                    "observed_rate": float(y[m].mean()),
                    "n": int(m.sum()),
                }
            )
    return {
        "model": info.__dict__,
        "overall": _metrics(p, y),
        "by_context": by_context,
        "calibration": calibration,
        "min_for_metrics": MIN_FOR_METRICS,
    }
