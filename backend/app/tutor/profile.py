"""Student profile, subjects, onboarding and learning goals.

`StudentProfile.subject_id` is the student's CURRENT subject. `Enrollment(user, subject)` lists
the subjects the student has started, and `Enrollment.diagnostic_completed_at` says whether
the placement check was done in that subject.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Enrollment, Subject, User
from app.tutor.models import Interaction, LearningGoal, Skill, SkillState, StudentProfile
from app.tutor.seed import SUBJECT_CODE
from app.tutor.subjects import V2_SUBJECTS

GOAL_DEFAULTS = {"strengthen_skills": 3, "weekly_practice": 30, "master_skill": 1}


def get(db: Session, user: User) -> StudentProfile | None:
    return db.get(StudentProfile, user.id)


def require(db: Session, user: User) -> StudentProfile:
    p = get(db, user)
    if p is None or p.onboarded_at is None:
        raise AppError(409, "onboarding_required", "Finish onboarding first.")
    return p


def active_subjects(db: Session) -> list[Subject]:
    return list(
        db.scalars(
            select(Subject)
            .where(Subject.is_active, Subject.code.in_(V2_SUBJECTS))
            .order_by(Subject.id)
        )
    )


def subject_by_code(db: Session, code: str) -> Subject:
    s = db.scalar(
        select(Subject).where(
            Subject.code == (code or "").upper(), Subject.is_active, Subject.code.in_(V2_SUBJECTS)
        )
    )
    if s is None:
        raise AppError(404, "subject_not_found", "That subject isn't available.")
    return s


def math_subject(db: Session) -> Subject:
    s = db.scalar(select(Subject).where(Subject.code == SUBJECT_CODE, Subject.is_active))
    if s is None:
        raise AppError(
            503,
            "content_missing",
            "Mathematics content hasn't been loaded yet (run scripts/seed_math.py).",
        )
    return s


def current_subject(db: Session, user: User) -> Subject:
    """The student's current subject (if still active), else Mathematics."""
    p = get(db, user)
    if p is not None and p.subject_id is not None:
        s = db.get(Subject, p.subject_id)
        if s is not None and s.is_active and s.code in V2_SUBJECTS:
            return s
    return math_subject(db)


def subject_of_skill(db: Session, skill: Skill) -> Subject:
    return db.get(Subject, skill.subject_id)


def enrollment(db: Session, user: User, subject: Subject) -> Enrollment | None:
    return db.get(Enrollment, (user.id, subject.id))


def enroll(db: Session, user: User, subject: Subject) -> Enrollment:
    e = enrollment(db, user, subject)
    if e is None:
        e = Enrollment(user_id=user.id, subject_id=subject.id)
        db.add(e)
        db.flush()
    return e


def diagnostic_done(db: Session, user: User, subject: Subject) -> bool:
    e = enrollment(db, user, subject)
    return bool(e and e.diagnostic_completed_at)


def mark_diagnostic_done(db: Session, user: User, subject: Subject, at: datetime) -> None:
    e = enroll(db, user, subject)
    e.diagnostic_completed_at = e.diagnostic_completed_at or at
    p = get(db, user)
    if p is not None:  # legacy field: the first subject's placement check
        p.diagnostic_completed_at = p.diagnostic_completed_at or at


def onboard(
    db: Session,
    user: User,
    goal_type: str,
    focus_skill_id: int | None,
    goal_kind: str,
    goal_target: int | None,
    subject_code: str | None = None,
    grade: int | None = None,
    pace_preference: str | None = None,
) -> StudentProfile:
    subject = subject_by_code(db, subject_code) if subject_code else math_subject(db)
    if goal_type == "learn_topic":
        skill = db.get(Skill, focus_skill_id) if focus_skill_id else None
        if skill is None or not skill.is_available or skill.subject_id != subject.id:
            raise AppError(422, "validation_error", "Choose a topic to learn.")
    p = get(db, user) or StudentProfile(user_id=user.id)
    p.subject_id = subject.id
    p.goal_type = goal_type
    p.focus_skill_id = focus_skill_id if goal_type == "learn_topic" else None
    p.grade = grade
    if pace_preference:
        p.pace_preference = pace_preference
    p.onboarded_at = p.onboarded_at or datetime.now(UTC)
    db.add(p)
    db.flush()
    enroll(db, user, subject)
    set_goal(
        db, user, goal_kind, goal_target, focus_skill_id if goal_kind == "master_skill" else None
    )
    db.commit()
    return p


def check_update(db: Session, p: StudentProfile, data: dict) -> None:
    """The same rules as onboarding, for a profile edit: a focus topic must be an available
    skill of the current subject, and "learn a topic" needs one."""
    if data.get("focus_skill_id") is not None:
        skill = db.get(Skill, data["focus_skill_id"])
        if skill is None or not skill.is_available or skill.subject_id != p.subject_id:
            raise AppError(422, "validation_error", "Choose a topic from your current subject.")
    goal_type = data.get("goal_type", p.goal_type)
    focus = data.get("focus_skill_id", p.focus_skill_id)
    if goal_type == "learn_topic" and focus is None:
        raise AppError(422, "validation_error", "Choose a topic to learn.")


def set_subject(db: Session, user: User, code: str) -> StudentProfile:
    """Switch the current subject (enrolling in it the first time)."""
    p = require(db, user)
    subject = subject_by_code(db, code)
    enroll(db, user, subject)
    if p.subject_id != subject.id:
        p.subject_id = subject.id
        p.current_skill_id = None
        if p.focus_skill_id is not None:
            focus = db.get(Skill, p.focus_skill_id)
            if focus is None or focus.subject_id != subject.id:
                p.focus_skill_id = None
                if p.goal_type == "learn_topic":
                    p.goal_type = "assess_overall"
    db.flush()
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
    """Progress toward the active goal. Weekly practice counts every subject; skill goals
    count the skills of every subject too (a goal belongs to the student, not a subject)."""
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
        label = f"Build {g.target} strong skills"
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
    subject = None
    if p and p.subject_id:
        subject = db.get(Subject, p.subject_id)
    enrolled = (
        list(
            db.scalars(
                select(Subject.code)
                .join(Enrollment, Enrollment.subject_id == Subject.id)
                .where(
                    Enrollment.user_id == user.id,
                    Subject.is_active,
                    Subject.code.in_(V2_SUBJECTS),
                )
                .order_by(Subject.id)
            )
        )
        if p
        else []
    )
    return {
        "full_name": user.full_name,
        "email": user.email,
        "subject": subject.name if subject else None,
        "subject_code": subject.code if subject else None,
        "grade": p.grade if p else None,
        "subjects_enrolled": enrolled,
        "onboarded": bool(p and p.onboarded_at),
        "diagnostic_completed": bool(subject and diagnostic_done(db, user, subject)),
        "goal_type": p.goal_type if p else None,
        "focus_skill": {"id": focus.id, "name": focus.name, "code": focus.code} if focus else None,
        "pace_preference": p.pace_preference if p else "balanced",
        "hints_enabled": p.hints_enabled if p else True,
        "daily_goal": p.daily_goal if p else 10,
        "goal": goal_progress(db, user) if p else None,
        "is_admin": is_admin(user),
    }


def subjects_out(db: Session, user: User) -> list[dict]:
    """GET /subjects: every active subject with the student's state in it."""
    from app.tutor import kt
    from app.tutor.subjects import meta

    p = get(db, user)
    enrolled = {
        e.subject_id: e for e in db.scalars(select(Enrollment).where(Enrollment.user_id == user.id))
    }
    counts = dict(
        db.execute(
            select(Skill.subject_id, func.count())
            .where(Skill.is_available)
            .group_by(Skill.subject_id)
        ).all()
    )
    questions = dict(
        db.execute(
            select(Skill.subject_id, func.coalesce(func.sum(Skill.n_items), 0))
            .where(Skill.is_available)
            .group_by(Skill.subject_id)
        ).all()
    )
    out_ = []
    for s in active_subjects(db):
        m = meta(s.code)
        e = enrolled.get(s.id)
        out_.append(
            {
                "code": s.code,
                "name": s.name,
                "description": s.description,
                "n_skills": int(counts.get(s.id, 0)),
                "n_questions": int(questions.get(s.id, 0)),
                "enrolled": e is not None,
                "diagnostic_completed": bool(e and e.diagnostic_completed_at),
                "current": bool(p and p.subject_id == s.id),
                "has_model": kt.get_model(s.code) is not None,
                "grades": m["grades"],
                "attribution": m["attribution"],
                "notice": m["notice"],
            }
        )
    return out_


def is_admin(user: User) -> bool:
    from app.services.pilot import is_admin as _is_admin

    return _is_admin(user)
