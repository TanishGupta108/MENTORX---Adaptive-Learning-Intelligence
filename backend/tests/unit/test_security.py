import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core import security
from app.core.config import get_settings
from app.core.rate_limit import RateLimiter


def test_password_hash_roundtrip():
    h = security.hash_password("s3cret-pass")
    assert security.verify_password("s3cret-pass", h)
    assert not security.verify_password("wrong", h)
    assert not security.verify_password("s3cret-pass", None)


def test_access_token_roundtrip_and_tampering():
    uid = uuid.uuid4()
    token = security.create_access_token(uid, "student")
    assert security.decode_access_token(token)["sub"] == str(uid)
    with pytest.raises(security.InvalidToken):
        security.decode_access_token(token[:-2] + "xx")


def test_expired_and_wrong_type_tokens_are_rejected():
    s = get_settings()
    past = datetime.now(UTC) - timedelta(minutes=5)
    expired = jwt.encode({"sub": "x", "type": "access", "exp": past}, s.jwt_secret, s.jwt_algorithm)
    with pytest.raises(security.InvalidToken):
        security.decode_access_token(expired)
    future = datetime.now(UTC) + timedelta(minutes=5)
    other = jwt.encode(
        {"sub": "x", "type": "refresh", "exp": future}, s.jwt_secret, s.jwt_algorithm
    )
    with pytest.raises(security.InvalidToken):
        security.decode_access_token(other)


def test_refresh_tokens_are_random_and_only_hash_is_kept():
    a, ha = security.new_refresh_token()
    b, hb = security.new_refresh_token()
    assert a != b and ha != hb
    assert security.hash_refresh_token(a) == ha and len(ha) == 64


def test_rate_limiter_sliding_window():
    rl = RateLimiter(limit=2, window_seconds=60)
    assert rl.hit("k", now=0) and rl.hit("k", now=1)
    assert not rl.hit("k", now=2)
    assert rl.retry_after("k", now=2) == 59
    assert rl.hit("k", now=61)  # first hit has left the window


def test_production_rejects_insecure_settings(monkeypatch):
    from app.core.config import Settings

    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(environment="production", cookie_secure=True)
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(environment="production", jwt_secret="x" * 40, cookie_secure=False)
    ok = Settings(environment="production", jwt_secret="x" * 40, cookie_secure=True)
    assert ok.include_draft_questions is False
