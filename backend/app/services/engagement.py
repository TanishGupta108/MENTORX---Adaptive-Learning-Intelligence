"""Daily goal, streaks, weekly report (FR-ENG-01..03, 05) and feedback (FR-PILOT-03).

See docs/modules/engagement.md. Days are the student's local days.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.rate_limit import RateLimiter
from app.db.models import Attempt, Concept, Feedback, GoalDay, MasterySnapshot, User
from app.schemas.engagement import (
    ConceptChange,
    FeedbackOut,
    FeedbackRequest,
    GoalProgress,
    StreakOut,
    WeeklyOut,
)
from app.services import dashboard, learning

WEEK_DAYS = 7
IMPROVED_DELTA = 0.05  # a concept "improved" if its mastery rose at least this much

feedback_limiter = RateLimiter(limit=10, window_seconds=3600)


# ---------------------------------------------------------------- streaks


def streaks(met: set[date], today: date) -> tuple[int, int]:
    """(current, longest) streak from the set of days the goal was met.

    The current streak ends today if today is met, otherwise yesterday: a streak stays alive
    until the end of the day on which it would break.
    """
    end = today if today in met else today - timedelta(days=1)
    current = 0
    while end - timedelta(days=current) in met:
        current += 1
    longest = run = 0
    prev = None
    for d in sorted(met):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return current, longest


def _today_valid(db: Session, user: User, today: date) -> int:
    day = dashboard.local_day(user, Attempt.created_at)
    return db.scalar(
        select(func.count()).where(Attempt.user_id == user.id, Attempt.is_valid, day == today)
    )


def _met_days(db: Session, user: User) -> set[date]:
    return set(db.scalars(select(GoalDay.day).where(GoalDay.user_id == user.id)))


def record_progress(db: Session, user: User, now: datetime | None = None) -> GoalProgress:
    """Call after storing an answer (or changing the goal). Records today if the goal is met.

    Runs inside the caller's transaction; the caller commits.
    """
    today = dashboard.today(user, now)
    met = _met_days(db, user)
    count = _today_valid(db, user, today)
    just_met = False
    if today not in met and count >= user.daily_goal:
        # ON CONFLICT: two concurrent answers in different sessions may both reach the goal.
        db.execute(
            insert(GoalDay)
            .values(user_id=user.id, day=today, goal=user.daily_goal)
            .on_conflict_do_nothing()
        )
        met.add(today)
        just_met = True
    current, _ = streaks(met, today)
    return GoalProgress(
        daily_goal=user.daily_goal,
        today_valid=count,
        goal_met_today=today in met,
        just_met=just_met,
        current_streak=current,
    )


def streak_status(db: Session, user: User) -> StreakOut:
    today = dashboard.today(user)
    met = _met_days(db, user)
    current, longest = streaks(met, today)
    return StreakOut(
        daily_goal=user.daily_goal,
        today_valid=_today_valid(db, user, today),
        goal_met_today=today in met,
        current_streak=current,
        longest_streak=longest,
        today=today,
        timezone=user.timezone,
    )


# ---------------------------------------------------------------- weekly report


def weekly(db: Session, user: User, code: str) -> WeeklyOut:
    subject = learning.subject_for(db, user, code)
    end = dashboard.today(user)
    start = end - timedelta(days=WEEK_DAYS - 1)

    a = dashboard._subject_attempts(subject.id).where(Attempt.user_id == user.id).subquery()
    day = dashboard.local_day(user, a.c.created_at)
    n, k = db.execute(
        select(func.count(), func.count().filter(a.c.is_correct)).where(day >= start)
    ).one()
    goal_days = db.scalar(
        select(func.count()).where(GoalDay.user_id == user.id, GoalDay.day >= start)
    )

    # Mastery per concept at the start of the week (latest snapshot before it) and now.
    snap_day = dashboard.local_day(user, MasterySnapshot.created_at)
    rows = db.execute(
        select(snap_day, Concept.code, Concept.name, MasterySnapshot.p_mastery)
        .join(Concept, Concept.id == MasterySnapshot.concept_id)
        .where(MasterySnapshot.user_id == user.id, Concept.subject_id == subject.id)
        .order_by(MasterySnapshot.created_at, MasterySnapshot.id)
    ).all()
    before: dict[str, float] = {}
    after: dict[str, float] = {}
    names: dict[str, str] = {}
    for d, c, name, p in rows:
        names[c] = name
        after[c] = p
        if d < start:
            before[c] = p
    both = sorted(set(before) & set(after))
    mean_start = sum(before[c] for c in both) / len(both) if both else None
    mean_end = sum(after[c] for c in both) / len(both) if both else None
    improved = sorted(
        (
            ConceptChange(concept=c, name=names[c], before=before[c], after=after[c])
            for c in both
            if after[c] - before[c] >= IMPROVED_DELTA
        ),
        key=lambda x: x.before - x.after,  # biggest gain first
    )
    return WeeklyOut(
        subject=subject.code,
        start=start,
        end=end,
        questions=n,
        accuracy=k / n if n else None,
        goal_days_met=goal_days,
        mean_mastery_start=mean_start,
        mean_mastery_end=mean_end,
        mastery_change=mean_end - mean_start if both else None,
        concepts_improved=improved,
    )


# ---------------------------------------------------------------- feedback


def submit_feedback(db: Session, user: User, req: FeedbackRequest) -> FeedbackOut:
    key = f"user:{user.id}"
    if not feedback_limiter.hit(key):
        raise AppError(
            429,
            "rate_limited",
            "Thanks! You've sent a lot of feedback recently. Please try again later.",
            headers={"Retry-After": str(feedback_limiter.retry_after(key))},
        )
    row = Feedback(
        user_id=user.id,
        rating=req.rating,
        category=req.category,
        message=req.message.strip(),
        page=req.page,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return FeedbackOut(id=row.id)
