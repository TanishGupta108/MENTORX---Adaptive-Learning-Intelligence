from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import DB, CurrentUser
from app.api.v1.auth import COOKIE_PATH
from app.core.config import get_settings
from app.schemas.auth import DeleteAccountRequest, UserOut, UserUpdate
from app.services import account

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def read_me(user: CurrentUser, db: DB) -> UserOut:
    return account.to_out(db, user)


@router.patch("", response_model=UserOut)
def update_me(req: UserUpdate, user: CurrentUser, db: DB) -> UserOut:
    return account.to_out(db, account.update_profile(db, user, req))


@router.get("/export")
def export_me(user: CurrentUser, db: DB) -> JSONResponse:
    return JSONResponse(
        account.export_data(db, user),
        headers={"Content-Disposition": 'attachment; filename="mentorx-my-data.json"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(req: DeleteAccountRequest, user: CurrentUser, db: DB, response: Response) -> Response:
    account.delete_account(db, user, str(req.confirm_email))
    response.delete_cookie(get_settings().refresh_cookie_name, path=COOKIE_PATH)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
