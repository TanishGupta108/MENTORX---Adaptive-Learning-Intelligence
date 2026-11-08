from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser
from app.api.v1.learning import SubjectCode
from app.schemas.dashboard import ActivityOut, DashboardOut, FlagOut, FlagRequest, TrendsOut
from app.services import dashboard

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(subject: SubjectCode, user: CurrentUser, db: DB) -> DashboardOut:
    return dashboard.summary(db, user, subject)


@router.get("/dashboard/trends", response_model=TrendsOut)
def get_trends(
    subject: SubjectCode,
    user: CurrentUser,
    db: DB,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> TrendsOut:
    return dashboard.trends(db, user, subject, days)


@router.get("/dashboard/activity", response_model=ActivityOut)
def get_activity(
    user: CurrentUser, db: DB, weeks: Annotated[int, Query(ge=1, le=52)] = 12
) -> ActivityOut:
    return dashboard.activity(db, user, weeks)


@router.post(
    "/questions/{question_id}/flag", response_model=FlagOut, status_code=status.HTTP_201_CREATED
)
def flag_question(question_id: int, req: FlagRequest, user: CurrentUser, db: DB) -> FlagOut:
    """Report a problem with a question you've been shown."""
    return dashboard.flag_question(db, user, question_id, req.comment)
