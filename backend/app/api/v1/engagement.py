from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.api.v1.learning import SubjectCode
from app.schemas.engagement import FeedbackOut, FeedbackRequest, StreakOut, WeeklyOut
from app.services import engagement

router = APIRouter(tags=["engagement"])


@router.get("/engagement/streak", response_model=StreakOut)
def get_streak(user: CurrentUser, db: DB) -> StreakOut:
    """Daily goal progress, current and longest streak (FR-ENG-03)."""
    return engagement.streak_status(db, user)


@router.get("/engagement/weekly", response_model=WeeklyOut)
def get_weekly(subject: SubjectCode, user: CurrentUser, db: DB) -> WeeklyOut:
    """The last 7 days: questions, accuracy, goal days and mastery change (FR-ENG-05)."""
    return engagement.weekly(db, user, subject)


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def post_feedback(req: FeedbackRequest, user: CurrentUser, db: DB) -> FeedbackOut:
    """Send feedback from any page (FR-PILOT-03)."""
    return engagement.submit_feedback(db, user, req)
