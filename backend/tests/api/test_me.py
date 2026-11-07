"""FR-AUTH-08..11."""

from sqlalchemy import func, select

from app.db.models import Enrollment, RefreshToken, User
from tests.conftest import auth, register


def test_update_profile(client):
    h = auth(register(client))
    r = client.patch(
        "/api/v1/me",
        headers=h,
        json={"daily_goal": 25, "timezone": "Europe/London", "consent_research": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["daily_goal"], body["timezone"], body["consent_research"]) == (
        25,
        "Europe/London",
        True,
    )


def test_research_consent_defaults_to_off(client):
    h = auth(register(client))
    assert client.get("/api/v1/me", headers=h).json()["consent_research"] is False


def test_update_rejects_bad_values_and_unknown_fields(client):
    h = auth(register(client))
    assert client.patch("/api/v1/me", headers=h, json={"timezone": "Mars/Base"}).status_code == 422
    assert client.patch("/api/v1/me", headers=h, json={"daily_goal": 0}).status_code == 422
    assert client.patch("/api/v1/me", headers=h, json={"role": "admin"}).status_code == 422
    assert client.patch("/api/v1/me", headers=h, json={"full_name": None}).status_code == 422


def test_delete_requires_matching_email(client, db):
    h = auth(register(client, email="me@example.com"))
    r = client.request(
        "DELETE", "/api/v1/me", headers=h, json={"confirm_email": "other@example.com"}
    )
    assert r.status_code == 400
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_delete_removes_user_and_everything_they_own(client, db, seeded):
    h = auth(register(client, email="me@example.com"))
    client.post("/api/v1/subjects/ML/enroll", headers=h)
    r = client.request("DELETE", "/api/v1/me", headers=h, json={"confirm_email": "ME@example.com"})
    assert r.status_code == 204
    for model in (User, Enrollment, RefreshToken):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert client.get("/api/v1/me", headers=h).status_code == 401  # token no longer works


def test_export_contains_profile_and_enrollments(client, seeded):
    h = auth(register(client, email="me@example.com"))
    client.post("/api/v1/subjects/ML/enroll", headers=h)
    r = client.get("/api/v1/me/export", headers=h)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["email"] == "me@example.com"
    assert [e["subject"] for e in data["enrollments"]] == ["ML"]
    assert data["attempts"] == [] and data["mastery"] == []


def test_users_cannot_see_each_other(client):
    a = auth(register(client, email="a@example.com"))
    b = auth(register(client, email="b@example.com"))
    assert client.get("/api/v1/me", headers=a).json()["email"] == "a@example.com"
    assert client.get("/api/v1/me", headers=b).json()["email"] == "b@example.com"
