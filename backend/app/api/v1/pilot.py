from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser
from app.api.v1.learning import SubjectCode
from app.core.errors import AppError
from app.db.models import User
from app.schemas.pilot import PilotMetrics, PilotStatus, SusOut, SusRequest
from app.services import pilot

router = APIRouter(tags=["pilot"])


def _admin(user: CurrentUser) -> User:
    if not pilot.is_admin(user):
        raise AppError(403, "forbidden", "Only the study team can see this.")
    return user


AdminUser = Annotated[User, Depends(_admin)]


@router.get("/pilot/status", response_model=PilotStatus)
def get_status(subject: SubjectCode, user: CurrentUser, db: DB) -> PilotStatus:
    """What the study asks of this student next (FR-PILOT-02/04)."""
    return pilot.status(db, user, subject)


@router.post("/pilot/sus", response_model=SusOut, status_code=201)
def post_sus(subject: SubjectCode, req: SusRequest, user: CurrentUser, db: DB) -> SusOut:
    """The System Usability Scale questionnaire, after the post-test (FR-PILOT-04)."""
    return pilot.submit_sus(db, user, subject, req)


@router.get("/admin/pilot/metrics", response_model=PilotMetrics)
def get_metrics(_: AdminUser, db: DB) -> PilotMetrics:
    """FR-DASH-09: outcomes by group, engagement, live model quality, feedback."""
    return pilot.metrics(db)


def _csv(body: str, name: str) -> Response:
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/admin/export/attempts.csv")
def export_attempts(_: AdminUser, db: DB) -> Response:
    """FR-PILOT-05: pseudonymised answers of consenting students, for retraining."""
    return _csv(pilot.export_attempts(db), "mentorx-attempts.csv")


@router.get("/admin/export/outcomes.csv")
def export_outcomes(_: AdminUser, db: DB) -> Response:
    """Pseudonymised pre/post scores, gain and SUS per consenting participant."""
    return _csv(pilot.export_outcomes(db), "mentorx-outcomes.csv")
