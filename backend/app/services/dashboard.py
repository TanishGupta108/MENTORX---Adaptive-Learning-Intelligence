"""Dashboard data (FR-DASH-01..08) and question flags (FR-QUIZ-11).

Days are the student's local days (their time zone). Nothing here is a placeholder:
when there is no data, values are null or lists are empty (FR-DASH-08).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import (
    Attempt,
    Concept,
    Enrollment,
    MasterySnapshot,
    Question,
    QuestionFlag,
    StudySession,
    User,
)
from app.schemas.dashboard import (
    ActiveSession,
    ActivityDay,
    ActivityOut,
    ConceptMastery,
    DashboardOut,
    FlagOut,
    TrendPoint,
    TrendsOut,
)
from app.services import learning

MIN_ATTEMPTS_FOR_RANKING = 3  # FR-DASH-03


def local_day(user: User, col):
    """SQL expression: the student's local calendar date of a timestamptz column."""
    return cast(func.timezone(user.timezone, col), Date)


def today(user: User, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(user.timezone)).date()


def _subject_attempts(subject_id: int):
    return (
        select(Attempt)
        .join(Question, Question.id == Attempt.question_id)
        .join(Concept, Concept.id == Question.concept_id)
        .where(Concept.subject_id == subject_id)
    )


def summary(db: Session, user: User, code: str) -> DashboardOut:
    cfg = get_settings()
    subject = learning.subject_for(db, user, code)
    states = learning.states(db, user, subject.id, datetime.now(UTC))
    db.commit()  # stale mastery may have been refreshed
    assessed = [s for s in states.values() if s.peak is not None]  # stored estimates only
    ranked = sorted(
        (s for s in assessed if s.n_attempts >= MIN_ATTEMPTS_FOR_RANKING),
        key=lambda s: (s.p, s.concept.topo_order),
    )

    def cm(s):
        return ConceptMastery(
            concept=s.concept.code, name=s.concept.name, mastery=s.p, n_attempts=s.n_attempts
        )

    attempts = _subject_attempts(subject.id).where(Attempt.user_id == user.id).subquery()
    n, k = db.execute(select(func.count(), func.count().filter(attempts.c.is_correct))).one()
    enrollment = db.get(Enrollment, (user.id, subject.id))
    sessions = db.scalars(
        select(StudySession).where(
            StudySession.user_id == user.id, StudySession.subject_id == subject.id
        )
    ).all()
    return DashboardOut(
        subject=subject.code,
        diagnostic_completed=enrollment.diagnostic_completed_at is not None,
        concepts_total=len(states),
        concepts_assessed=len(assessed),
        concepts_mastered=sum(s.p >= cfg.mastered_threshold for s in assessed),
        mastered_threshold=cfg.mastered_threshold,
        mean_mastery=sum(s.p for s in assessed) / len(assessed) if assessed else None,
        questions_answered=n,
        accuracy=k / n if n else None,
        sessions_completed=sum(s.status == "completed" for s in sessions),
        strongest=[cm(s) for s in reversed(ranked[-3:])],
        weakest=[cm(s) for s in ranked[:3]],
        active_sessions=[
            ActiveSession(id=s.id, type=s.type, answered=s.answered_count, target=s.target_count)
            for s in sessions
            if s.status == "active"
        ],
    )


def trends(db: Session, user: User, code: str, days: int) -> TrendsOut:
    """FR-DASH-04: daily accuracy and end-of-day mean mastery, last `days` days."""
    subject = learning.subject_for(db, user, code)
    end = today(user)
    start = end - timedelta(days=days - 1)
    a = _subject_attempts(subject.id).where(Attempt.user_id == user.id).subquery()
    day = local_day(user, a.c.created_at)
    per_day = {
        d: (int(n), int(k))
        for d, n, k in db.execute(
            select(day, func.count(), func.count().filter(a.c.is_correct))
            .where(day >= start)
            .group_by(day)
        )
    }

    # Mean mastery at the end of each day = mean over concepts of their latest snapshot.
    snap_day = local_day(user, MasterySnapshot.created_at)
    snaps = db.execute(
        select(snap_day, MasterySnapshot.concept_id, MasterySnapshot.p_mastery)
        .join(Concept, Concept.id == MasterySnapshot.concept_id)
        .where(
            MasterySnapshot.user_id == user.id,
            Concept.subject_id == subject.id,
            snap_day <= end,
        )
        .order_by(MasterySnapshot.created_at, MasterySnapshot.id)
    ).all()
    latest: dict[int, float] = {}
    i = 0
    points = []
    for offset in range(days):
        d = start + timedelta(days=offset)
        while i < len(snaps) and snaps[i][0] <= d:
            latest[snaps[i][1]] = snaps[i][2]
            i += 1
        n, k = per_day.get(d, (0, 0))
        points.append(
            TrendPoint(
                day=d,
                answered=n,
                accuracy=k / n if n else None,
                mean_mastery=sum(latest.values()) / len(latest) if latest else None,
            )
        )
    return TrendsOut(subject=subject.code, days=days, points=points)


def activity(db: Session, user: User, weeks: int) -> ActivityOut:
    """FR-DASH-07: questions answered per local day, every subject, last `weeks` weeks."""
    end = today(user)
    start = end - timedelta(days=weeks * 7 - 1)
    day = local_day(user, Attempt.created_at)
    counts = dict(
        db.execute(
            select(day, func.count()).where(Attempt.user_id == user.id, day >= start).group_by(day)
        ).all()
    )
    return ActivityOut(
        weeks=weeks,
        timezone=user.timezone,
        days=[
            ActivityDay(day=d, answered=int(counts.get(d, 0)))
            for d in (start + timedelta(days=i) for i in range((end - start).days + 1))
        ],
    )


def daily_counts(db: Session, user: User, valid_only: bool = True) -> dict[date, int]:
    day = local_day(user, Attempt.created_at)
    stmt = select(day, func.count()).where(Attempt.user_id == user.id)
    if valid_only:
        stmt = stmt.where(Attempt.is_valid)
    return {d: int(n) for d, n in db.execute(stmt.group_by(day))}


def flag_question(db: Session, user: User, question_id: int, comment: str) -> FlagOut:
    """FR-QUIZ-11. Only questions the student has actually been shown can be flagged."""
    seen = db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.user_id == user.id, Attempt.question_id == question_id)
    ) or db.scalar(
        select(func.count())
        .select_from(StudySession)
        .where(StudySession.user_id == user.id, StudySession.current_question_id == question_id)
    )
    if not seen:
        raise AppError(404, "question_not_found", "Question not found.")
    flag = QuestionFlag(user_id=user.id, question_id=question_id, comment=comment.strip())
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return FlagOut(id=flag.id, question_id=question_id, status=flag.status)
