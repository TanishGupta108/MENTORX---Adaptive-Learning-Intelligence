"""M9 hardening: security headers, rate limits, production config."""

import pytest

from app.core.config import DEV_JWT_SECRET, Settings
from tests.conftest import register


def test_security_headers_on_api_responses(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert r.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in r.headers  # only in production (HTTPS)


def test_hsts_and_no_docs_in_production(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core import config
    from app.main import create_app

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 48)
    monkeypatch.setenv("COOKIE_SECURE", "true")
    config.get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/v1/health")
            assert r.headers["Strict-Transport-Security"].startswith("max-age=")
            assert c.get("/docs").status_code == 404
            assert c.get("/openapi.json").status_code == 404
    finally:
        config.get_settings.cache_clear()


def test_registration_is_rate_limited_per_ip(client, seeded):
    from app.services.auth import register_limiter

    for i in range(register_limiter.limit):
        register(client, email=f"user{i}@example.com")
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "one-too-many@example.com",
            "password": "correct horse 1",
            "full_name": "Spam Bot",
            "privacy_accepted": True,
        },
    )
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0


def test_registration_has_a_site_wide_cap_that_fake_ips_cannot_dodge(monkeypatch):
    """A client calling the API host directly can fake X-Forwarded-For, so every request looks
    like a new IP; the site-wide hourly cap still stops it."""
    from app.core.errors import AppError
    from app.services import auth as auth_service

    monkeypatch.setattr(auth_service.register_global_limiter, "limit", 3)
    for i in range(3):
        auth_service.check_registration_rate(f"203.0.113.{i}")
    with pytest.raises(AppError) as exc:
        auth_service.check_registration_rate("203.0.113.99")
    assert exc.value.status_code == 429


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_hosted_database_urls_get_the_psycopg_driver(given, expected):
    assert Settings(database_url=given).database_url == expected


def test_production_rejects_insecure_settings():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(environment="production", jwt_secret=DEV_JWT_SECRET, cookie_secure=True)
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(environment="production", jwt_secret="y" * 48, cookie_secure=False)


def test_request_id_is_echoed_only_when_safe(client):
    assert (
        client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    forged = client.get("/api/v1/health", headers={"X-Request-ID": "x" * 65})
    assert forged.headers["X-Request-ID"] != "x" * 65  # replaced by a generated ID


def test_json_logs_carry_the_request_id():
    import json
    import logging

    from app.core.errors import request_id_var
    from app.core.logging import JsonFormatter, RequestIdFilter

    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    token = request_id_var.set("rid-42")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == "rid-42"
    assert entry["message"] == "hello world" and entry["level"] == "INFO"


def test_empty_environment_variables_mean_default(monkeypatch):
    """A cleared value in the hosting dashboard (e.g. SEED_INCLUDE_DRAFTS=) must not crash
    start-up: empty counts as unset."""
    for var in ("SEED_INCLUDE_DRAFTS", "EXPOSE_DOCS", "POSTTEST_OPEN", "ADMIN_EMAILS"):
        monkeypatch.setenv(var, "")
    s = Settings()
    assert s.seed_include_drafts is None and s.expose_docs is None
    assert s.posttest_open is False and s.admin_email_set == set()
