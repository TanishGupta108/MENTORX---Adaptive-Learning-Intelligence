"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import AppError
from app.db.models import User
from app.db.session import get_db

DB = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = AppError(
    401, "unauthenticated", "Please log in.", headers={"WWW-Authenticate": "Bearer"}
)


def get_current_user(
    db: DB, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _UNAUTHENTICATED
    try:
        payload = security.decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (security.InvalidToken, ValueError) as exc:
        raise _UNAUTHENTICATED from exc
    user = db.get(User, user_id)
    if user is None:  # e.g. the account was deleted after the token was issued
        raise _UNAUTHENTICATED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
