"""Health checks. /health = process is up; /health/ready = database is reachable too."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


class ModelHealth(BaseModel):
    available: bool
    name: str | None = None
    display_name: str | None = None
    test_auc: float | None = None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def ready(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Readiness check failed: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return HealthResponse(status="ok")


@router.get("/health/model", response_model=ModelHealth)
def model_health() -> ModelHealth:
    """Is the knowledge-tracing model loaded? (If not, the app shows observed data only.)"""
    from app.tutor import kt

    i = kt.info()
    return ModelHealth(
        available=i.available, name=i.name, display_name=i.display_name, test_auc=i.test_auc
    )
