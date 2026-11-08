"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    auth,
    dashboard,
    engagement,
    health,
    learning,
    me,
    pilot,
    sessions,
    subjects,
)
from app.core import errors, headers
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_production)

    # Interactive docs are off in production unless explicitly enabled (smaller attack surface).
    docs = settings.expose_docs if settings.expose_docs is not None else not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="0.6.0",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    errors.install(app)
    headers.install(app, settings.is_production)
    for router in (
        health.router,
        auth.router,
        me.router,
        subjects.router,
        sessions.router,
        learning.router,
        dashboard.router,
        engagement.router,
        pilot.router,
    ):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
