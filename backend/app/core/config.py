"""Application settings, loaded from environment variables (and a local .env file)."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MENTORX API"
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://mentorx:mentorx@localhost:5432/mentorx"

    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:5173"

    # --- auth (FR-AUTH-04/05/07) ---
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=30)
    refresh_cookie_name: str = "mentorx_refresh"
    # In production the frontend calls the API through a same-origin proxy (Vercel rewrite),
    # so a Strict, Secure, path-scoped cookie works. Plain-HTTP local dev needs secure=False.
    cookie_secure: bool = False
    cookie_samesite: str = Field(default="strict", pattern="^(strict|lax|none)$")
    login_attempts_per_minute: int = 5

    # --- content ---
    # Draft (unreviewed) questions are loaded only outside production (see question-bank guide).
    seed_include_drafts: bool | None = None

    # --- pilot (FR-PILOT-01) ---
    pilot_active: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def include_draft_questions(self) -> bool:
        if self.seed_include_drafts is not None:
            return self.seed_include_drafts
        return self.environment != "production"

    @model_validator(mode="after")
    def production_must_be_secure(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to a random value of 32+ chars in production"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
