"""Application settings, loaded from environment variables (and a local .env file)."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789"


class Settings(BaseSettings):
    # env_ignore_empty: a variable that exists but is empty (as hosting dashboards store a
    # cleared value) means "use the default", instead of failing to parse "" as a bool.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    app_name: str = "MENTORX API"
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    log_level: str = "INFO"
    expose_docs: bool | None = None  # default: on outside production, off in production

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
    registrations_per_hour: int = 10  # per client IP

    # --- content ---
    # Draft (unreviewed) questions are loaded only outside production (see question-bank guide).
    seed_include_drafts: bool | None = None

    # --- pilot (FR-PILOT-01..05, docs/modules/pilot.md) ---
    pilot_active: bool = False  # new sign-ups get an experiment group and a pre-test form
    posttest_open: bool = False  # set at the end of the pilot window
    admin_emails: str = ""  # comma-separated; these accounts can see pilot metrics and exports

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # --- learning engine (tunable; see docs/srs/SRS.md FR-QUIZ, FR-REV, FR-ENG) ---
    model_artifacts_dir: str = "model_artifacts"
    target_p_correct: float = Field(default=0.65, gt=0, lt=1)  # FR-QUIZ-02
    selection_top_k: int = Field(default=3, ge=1)  # random choice among k closest to target
    practice_length: int = Field(default=10, ge=1, le=50)  # FR-QUIZ-09
    recent_correct_exclusion_days: int = Field(default=7, ge=0)  # FR-QUIZ-03
    valid_answer_min_ms: int = Field(default=3000, ge=0)  # FR-ENG-02
    mastery_threshold: float = Field(default=0.6, gt=0, lt=1)  # prerequisite "met" (FR-PATH-02)
    mastered_threshold: float = Field(default=0.8, gt=0, lt=1)  # "mastered" (FR-DASH-01)
    revision_peak: float = Field(default=0.8, gt=0, lt=1)  # FR-REV-01: peak reached ...
    revision_floor: float = Field(default=0.6, gt=0, lt=1)  # ... and current fell below this
    revision_length: int = Field(default=5, ge=1, le=50)  # FR-REV-03
    path_length: int = Field(default=5, ge=1, le=20)  # FR-PATH-01
    practice_path_concepts: int = Field(default=3, ge=1)  # recommended practice draws from these
    mastery_stale_hours: float = Field(default=24, gt=0)  # FR-KT-04: recompute on read if older
    revision_projection_days: int = Field(default=180, ge=1)  # FR-REV-05 horizon
    # Other students' answers feed question difficulty at most this many seconds late.
    difficulty_cache_seconds: float = Field(default=60, ge=0)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, v: str) -> str:
        """Hosts (Render, Neon) hand out postgres:// URLs; SQLAlchemy needs the driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

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
