"""FR-AUTH-01..07, NFR-SEC-03."""

from sqlalchemy import select

from app.db.models import RefreshToken, User
from tests.conftest import auth, register

COOKIE = "mentorx_refresh"


def test_register_returns_token_and_sets_httponly_refresh_cookie(client):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "a@example.com",
            "password": "longenough1",
            "full_name": "  Asha   Rao ",
            "privacy_accepted": True,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 30 * 60
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie and "SameSite=strict" in cookie
    me = client.get("/api/v1/me", headers=auth(body["access_token"])).json()
    assert me["full_name"] == "Asha Rao"  # whitespace normalised


def test_password_is_stored_as_argon2_hash(client, db):
    register(client, password="my secret pw")
    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert "my secret pw" not in user.password_hash


def test_duplicate_email_is_rejected_case_insensitively(client):
    register(client, email="dup@example.com")
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUP@Example.com",
            "password": "longenough1",
            "full_name": "X",
            "privacy_accepted": True,
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_registration_requires_privacy_acceptance_and_valid_fields(client):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "short",
            "full_name": "",
            "privacy_accepted": False,
        },
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and err["request_id"]
    assert {f["field"] for f in err["fields"]} == {
        "email",
        "password",
        "full_name",
        "privacy_accepted",
    }


def test_login_errors_do_not_reveal_whether_email_exists(client):
    register(client, email="known@example.com", password="right password")
    wrong_pw = client.post(
        "/api/v1/auth/login", json={"email": "known@example.com", "password": "nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"}
    )
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"]
    ok = client.post(
        "/api/v1/auth/login", json={"email": "KNOWN@example.com", "password": "right password"}
    )
    assert ok.status_code == 200


def test_login_is_rate_limited(client):
    register(client, email="victim@example.com")
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": "victim@example.com", "password": "x"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "victim@example.com", "password": "x"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


def test_protected_endpoint_requires_valid_token(client):
    assert client.get("/api/v1/me").status_code == 401
    r = client.get("/api/v1/me", headers=auth("not.a.jwt"))
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_refresh_rotates_token(client, db):
    register(client)
    old = client.cookies.get(COOKIE)
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    new = client.cookies.get(COOKIE)
    assert new and new != old
    rows = db.scalars(select(RefreshToken).order_by(RefreshToken.created_at)).all()
    assert rows[0].revoked_at is not None and rows[0].replaced_by_id == rows[1].id


def test_reusing_a_rotated_refresh_token_revokes_every_session(client):
    register(client)
    stolen = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    legit = client.cookies.get(COOKIE)

    client.cookies.set(COOKIE, stolen, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401  # reuse detected

    client.cookies.set(COOKIE, legit, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401  # family revoked too


def test_logout_revokes_refresh_token(client):
    register(client)
    token = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set(COOKIE, token, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_without_cookie_is_401(client):
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_refresh"
