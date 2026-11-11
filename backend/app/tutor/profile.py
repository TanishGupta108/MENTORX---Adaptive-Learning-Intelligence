"""Student profile, onboarding and learning goals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Enrollment, Subject, User
from app.tutor.models import Interaction, LearningGoal, Skill, SkillState, StudentProfile
from app.tutor.seed import SUBJECT_CODE

GOAL_DEFAULTS = {"strengthen_skills": 3, "weekly_practice": 30, "master_skill": 1}


def get(db: Session, user: User) -> StudentProfile | None:
    return db.get(StudentProfile, user.id)


def require(db: Session, user: User) -> StudentProfile:
    p = get(db, user)
    if p is None or p.onboarded_at is None:
        raise AppError(409, "onboarding_required", "Finish onboarding first.")
    return p


def math_subject(db: Session) -> Subject:
    s = db.scalar(select(Subject).where(Subject.code == SUBJECT_CODE, Subject.is_active))
    if s is None:
        raise AppError(
            503,
            "content_missing",
            "Mathematics content hasn't been loaded yet (run scripts/seed_math.py).",
        )
    return s


def onboard(
    db: Session,
    user: User,
    goal_type: str,
    focus_skill_id: int | None,
    goal_kind: str,
    goal_target: int | None,
) -> StudentProfile:
    subject = math_subject(db)
    if goal_type == "learn_topic":
        skill = db.get(Skill, focus_skill_id) if focus_skill_id else None
        if skill is None or not skill.is_available:
            raise AppError(422, "validation_error", "Choose a topic to learn.")
    p = get(db, user) or StudentProfile(user_id=user.id)
    p.subject_id = subject.id
    p.goal_type = goal_type
    p.focus_skill_id = focus_skill_id if goal_type == "learn_topic" else None
    p.onboarded_at = p.onboarded_at or datetime.now(UTC)
    db.add(p)
    if db.get(Enrollment, (user.id, subject.id)) is None:
        db.add(Enrollment(user_id=user.id, subject_id=subject.id))
    set_goal(
        db, user, goal_kind, goal_target, focus_skill_id if goal_kind == "master_skill" else None
    )
    db.commit()
    return p


def set_goal(
    db: Session, user: User, kind: str, target: int | None, skill_id: int | None
) -> LearningGoal:
    for g in db.scalars(
        select(LearningGoal).where(LearningGoal.user_id == user.id, LearningGoal.is_active)
    ):
        g.is_active = False
    g = LearningGoal(
        user_id=user.id, kind=kind, target=target or GOAL_DEFAULTS[kind], skill_id=skill_id
    )
    db.add(g)
    db.flush()
    return g


def goal_progress(db: Session, user: User) -> dict | None:
    g = db.scalar(
        select(LearningGoal)
        .where(LearningGoal.user_id == user.id, LearningGoal.is_active)
        .order_by(LearningGoal.id.desc())
    )
    if g is None:
        return None
    now = datetime.now(UTC)
    if g.kind == "weekly_practice":
        since = now - timedelta(days=7)
        value = db.scalar(
            select(func.count())
            .select_from(Interaction)
            .where(Interaction.user_id == user.id, Interaction.created_at >= since)
        )
        label = f"Answer {g.target} questions in 7 days"
    elif g.kind == "strengthen_skills":
        value = db.scalar(
            select(func.count())
            .select_from(SkillState)
            .where(SkillState.user_id == user.id, SkillState.status == "likely_strength")
        )
        label = f"Build {g.target} likely strengths"
    else:
        st = db.get(SkillState, (user.id, g.skill_id)) if g.skill_id else None
        skill = db.get(Skill, g.skill_id) if g.skill_id else None
        value = 1 if st and st.completed_at else 0
        label = f"Complete {skill.name}" if skill else "Complete your focus topic"
    value = int(value or 0)
    if value >= g.target and g.achieved_at is None:
        g.achieved_at = now
    return {
        "id": g.id,
        "kind": g.kind,
        "label": label,
        "target": g.target,
        "value": min(value, g.target),
        "achieved": value >= g.target,
        "skill_id": g.skill_id,
    }


def out(db: Session, user: User) -> dict:
    p = get(db, user)
    focus = db.get(Skill, p.focus_skill_id) if p and p.focus_skill_id else None
    return {
        "full_name": user.full_name,
        "email": user.email,
        "subject": "Mathematics" if p and p.subject_id else None,
        "onboarded": bool(p and p.onboarded_at),
        "diagnostic_completed": bool(p and p.diagnostic_completed_at),
        "goal_type": p.goal_type if p else None,
        "focus_skill": {"id": focus.id, "name": focus.name, "code": focus.code} if focus else None,
        "pace_preference": p.pace_preference if p else "balanced",
        "hints_enabled": p.hints_enabled if p else True,
        "goal": goal_progress(db, user) if p else None,
        "is_admin": is_admin(user),
    }


def is_admin(user: User) -> bool:
    from app.services.pilot import is_admin as _is_admin

    return _is_admin(user)
