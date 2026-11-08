"""Profile, data export and account deletion (FR-AUTH-08..11)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    Attempt,
    Concept,
    Enrollment,
    Feedback,
    GoalDay,
    Mastery,
    Question,
    StudySession,
    Subject,
    User,
)
from app.schemas.auth import UserOut, UserUpdate
from app.services import engagement


def to_out(db: Session, user: User) -> UserOut:
    codes = db.scalars(
        select(Subject.code)
        .join(Enrollment, Enrollment.subject_id == Subject.id)
        .where(Enrollment.user_id == user.id)
        .order_by(Subject.code)
    ).all()
    out = UserOut.model_validate(user)
    out.enrolled_subjects = list(codes)
    if user.email.lower() in get_settings().admin_email_set:
        out.role = "admin"  # study team members listed in ADMIN_EMAILS
    return out


def update_profile(db: Session, user: User, req: UserUpdate) -> User:
    for field, value in req.model_dump(exclude_unset=True).items():
        if value is None:
            raise AppError(422, "validation_error", f"{field} cannot be null.")
        setattr(user, field, " ".join(value.split()) if field == "full_name" else value)
    if {"daily_goal", "timezone"} & req.model_fields_set:
        db.flush()
        engagement.record_progress(db, user)  # e.g. a lowered goal is already met today
    db.commit()
    db.refresh(user)
    return user


def delete_account(db: Session, user: User, confirm_email: str) -> None:
    if confirm_email.lower() != user.email.lower():
        raise AppError(
            400, "confirmation_mismatch", "The email you typed doesn't match your account."
        )
    # Every user-owned table cascades from users (see db/models.py).
    db.execute(delete(User).where(User.id == user.id))
    db.commit()


def export_data(db: Session, user: User) -> dict:
    """Everything stored about the user, as plain JSON-able data (FR-AUTH-10)."""

    def iso(dt):
        return dt.isoformat() if dt else None

    enrollments = db.execute(
        select(Subject.code, Enrollment.enrolled_at, Enrollment.diagnostic_completed_at)
        .join(Subject, Subject.id == Enrollment.subject_id)
        .where(Enrollment.user_id == user.id)
    ).all()
    sessions = db.scalars(select(StudySession).where(StudySession.user_id == user.id)).all()
    attempts = db.execute(
        select(Attempt, Question.external_id)
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user.id)
        .order_by(Attempt.created_at)
    ).all()
    mastery = db.execute(
        select(Mastery, Concept.code)
        .join(Concept, Concept.id == Mastery.concept_id)
        .where(Mastery.user_id == user.id)
    ).all()
    feedback = db.scalars(select(Feedback).where(Feedback.user_id == user.id)).all()
    goal_days = db.scalars(
        select(GoalDay).where(GoalDay.user_id == user.id).order_by(GoalDay.day)
    ).all()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": to_out(db, user).model_dump(mode="json"),
        "enrollments": [
            {"subject": c, "enrolled_at": iso(e), "diagnostic_completed_at": iso(d)}
            for c, e, d in enrollments
        ],
        "sessions": [
            {
                "id": str(s.id),
                "type": s.type,
                "status": s.status,
                "answered": s.answered_count,
                "started_at": iso(s.started_at),
                "ended_at": iso(s.ended_at),
            }
            for s in sessions
        ],
        "attempts": [
            {
                "question": qid,
                "selected": a.selected_key,
                "correct": a.is_correct,
                "response_ms": a.response_ms,
                "at": iso(a.created_at),
            }
            for a, qid in attempts
        ],
        "mastery": [
            {
                "concept": code,
                "p_mastery": m.p_mastery,
                "n_attempts": m.n_attempts,
                "updated_at": iso(m.updated_at),
            }
            for m, code in mastery
        ],
        "feedback": [
            {
                "rating": f.rating,
                "category": f.category,
                "message": f.message,
                "page": f.page,
                "at": iso(f.created_at),
            }
            for f in feedback
        ],
        "goal_days": [{"day": g.day.isoformat(), "goal": g.goal} for g in goal_days],
    }
