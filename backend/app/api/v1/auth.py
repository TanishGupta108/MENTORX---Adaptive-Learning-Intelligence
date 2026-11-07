"""Auth endpoints. The refresh token lives only in an HttpOnly cookie scoped to /api/v1/auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import DB
from app.core.config import get_settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.refresh_cookie_name,
        token,
        max_age=s.refresh_token_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path=COOKIE_PATH,
    )


def _tokens(response: Response, tokens: auth_service.IssuedTokens) -> TokenResponse:
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


RefreshCookie = Annotated[str | None, Cookie(alias=get_settings().refresh_cookie_name)]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
def register(req: RegisterRequest, response: Response, db: DB) -> TokenResponse:
    _, tokens = auth_service.register(db, req)
    return _tokens(response, tokens)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, response: Response, db: DB) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    _, tokens = auth_service.login(db, str(req.email), req.password, ip)
    return _tokens(response, tokens)


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, db: DB, refresh_token: RefreshCookie = None) -> TokenResponse:
    _, tokens = auth_service.refresh(db, refresh_token)
    return _tokens(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DB, refresh_token: RefreshCookie = None) -> Response:
    auth_service.logout(db, refresh_token)
    response.delete_cookie(get_settings().refresh_cookie_name, path=COOKIE_PATH)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
