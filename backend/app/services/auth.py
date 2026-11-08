"""Registration, login, refresh-token rotation and logout (FR-AUTH-01..07)."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import RateLimiter
from app.db.models import RefreshToken, User
from app.schemas.auth import RegisterRequest

logger = logging.getLogger(__name__)

login_limiter = RateLimiter(limit=get_settings().login_attempts_per_minute, window_seconds=60)
register_limiter = RateLimiter(limit=get_settings().registrations_per_hour, window_seconds=3600)


def check_registration_rate(client_ip: str) -> None:
    """Slow down scripted sign-ups from one address (NFR-SEC)."""
    if not register_limiter.hit(f"ip:{client_ip}"):
        raise AppError(
            429,
            "rate_limited",
            "Too many accounts created from this network. Please try again later.",
            headers={"Retry-After": str(register_limiter.retry_after(f"ip:{client_ip}"))},
        )


INVALID_CREDENTIALS = AppError(401, "invalid_credentials", "Email or password is incorrect.")


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


def _issue(db: Session, user: User) -> IssuedTokens:
    s = get_settings()
    refresh_plain, refresh_hash = security.new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
        )
    )
    return IssuedTokens(
        access_token=security.create_access_token(user.id, user.role),
        refresh_token=refresh_plain,
        expires_in=s.access_token_minutes * 60,
    )


def register(db: Session, req: RegisterRequest) -> tuple[User, IssuedTokens]:
    s = get_settings()
    user = User(
        email=str(req.email),
        password_hash=security.hash_password(req.password),
        full_name=req.full_name,
        privacy_accepted_at=datetime.now(UTC),
    )
    if req.timezone:
        user.timezone = req.timezone
    if s.pilot_active:
        # FR-PILOT-01: random, permanent assignment; pre-test form counterbalanced too.
        user.experiment_group = random.SystemRandom().choice(["adaptive", "control"])
        user.pretest_form = random.SystemRandom().choice(["A", "B"])
    db.add(user)
    try:
        db.flush()  # the unique (case-insensitive) email constraint fires here
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "email_taken", "An account with this email already exists.") from exc
    tokens = _issue(db, user)
    db.commit()
    logger.info("user registered id=%s", user.id)
    return user, tokens


def login(db: Session, email: str, password: str, client_ip: str) -> tuple[User, IssuedTokens]:
    keys = (f"ip:{client_ip}", f"email:{email.lower()}")
    if not all(login_limiter.hit(k) for k in keys):
        retry = max(login_limiter.retry_after(k) for k in keys)
        raise AppError(
            429,
            "rate_limited",
            "Too many login attempts. Please try again in a minute.",
            headers={"Retry-After": str(retry)},
        )
    user = db.scalar(select(User).where(User.email == email))
    if not security.verify_password(password, user.password_hash if user else None):
        raise INVALID_CREDENTIALS
    tokens = _issue(db, user)
    db.commit()
    return user, tokens


def refresh(db: Session, refresh_token: str | None) -> tuple[User, IssuedTokens]:
    """Rotate a refresh token. Presenting an already-used token revokes the whole family."""
    unauthenticated = AppError(401, "invalid_refresh", "Your session has expired. Please log in.")
    if not refresh_token:
        raise unauthenticated
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == security.hash_refresh_token(refresh_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if row is None:
        raise unauthenticated
    if row.revoked_at is not None:
        # Reuse of a rotated token means it was probably stolen: log everyone out.
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        logger.warning("refresh token reuse detected user=%s; all sessions revoked", row.user_id)
        raise unauthenticated
    if row.expires_at <= now:
        raise unauthenticated
    user = db.get(User, row.user_id)
    if user is None:
        raise unauthenticated
    tokens = _issue(db, user)
    db.flush()
    new_row = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == security.hash_refresh_token(tokens.refresh_token)
        )
    )
    row.revoked_at = now
    row.replaced_by_id = new_row.id
    db.commit()
    return user, tokens


def logout(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == security.hash_refresh_token(refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
