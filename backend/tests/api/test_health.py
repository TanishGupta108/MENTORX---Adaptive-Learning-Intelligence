from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import create_app


def _client_with_db(url: str) -> TestClient:
    app = create_app()
    engine = create_engine(url)
    make_session = sessionmaker(bind=engine)

    def override():
        db = make_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_liveness():
    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok_when_database_reachable():
    client = _client_with_db("sqlite://")
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200


def test_readiness_503_when_database_unreachable():
    # Port 1 is never a Postgres server, so the connection fails fast.
    client = _client_with_db("postgresql+psycopg://x:x@127.0.0.1:1/x?connect_timeout=1")
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 503
