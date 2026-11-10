"""Test setup: a dedicated PostgreSQL database, migrated with Alembic, emptied between tests.

Uses TEST_DATABASE_URL if set, otherwise a `mentorx_test` database on the local
PostgreSQL server (see README, local setup). Tests never touch the development database.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+psycopg://mentorx:mentorx@localhost:5432/mentorx_test"
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["ENVIRONMENT"] = "test"
os.environ["PILOT_ACTIVE"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_URL = os.environ["TEST_DATABASE_URL"]


def _ensure_database() -> None:
    url = make_url(TEST_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    _ensure_database()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield cfg
    get_engine().dispose()


@pytest.fixture(autouse=True)
def clean_tables(migrated_database):
    yield
    engine = get_engine()
    with engine.begin() as conn:
        tables = conn.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    from app.ml.knowledge import reset_stats_cache
    from app.ml.registry import reset_cache
    from app.services.auth import login_limiter, register_limiter

    login_limiter.reset()
    register_limiter.reset()
    from app.services.engagement import feedback_limiter

    feedback_limiter.reset()
    reset_cache()
    reset_stats_cache()


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client():
    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def seeded(db):
    from app.content.question_bank import QUESTION_BANK_DIR, load_question_bank
    from app.content.seed import seed

    return seed(db, load_question_bank(QUESTION_BANK_DIR / "machine_learning"), include_drafts=True)


def register(client, email="student@example.com", password="correct horse 1", name="Asha Rao"):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": name, "privacy_accepted": True},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student(client, seeded):
    """A registered student enrolled in ML. Returns auth headers."""
    h = auth(register(client))
    assert client.post("/api/v1/subjects/ML/enroll", headers=h).status_code == 200
    return h
