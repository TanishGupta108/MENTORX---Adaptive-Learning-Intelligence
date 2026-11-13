"""Application settings, loaded from environment variables (and a local .env file)."""

import re
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
    # All sign-ups together. A backstop: a client calling the API host directly can fake its
    # IP (X-Forwarded-For), which defeats the per-IP limit but not this one.
    registrations_global_per_hour: int = 100

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

    # --- adaptive tutor (Mathematics on FoundationalASSIST, /api/v2) ---
    kt_artifacts_dir: str = "model_artifacts/foundationalassist"  # Mathematics (default)
    # One knowledge-tracing model per subject: "CODE=dir,CODE=dir". A subject without a model
    # (missing files) shows observed performance only. MATH uses kt_artifacts_dir unless named.
    kt_subjects: str = "GEO=model_artifacts/geography"
    kt_model: str = Field(default="dkt_q", pattern="^(dkt_q|dkt)$")  # which exported model serves
    diagnostic_length: int = Field(default=10, ge=3, le=30)  # overall diagnostic questions
    skill_check_length: int = Field(default=6, ge=3, le=20)  # diagnostic for one chosen skill
    reassessment_length: int = Field(default=5, ge=3, le=20)
    tutor_practice_length: int = Field(default=8, ge=3, le=30)
    strength_threshold: float = Field(default=0.75, gt=0, lt=1)  # observed accuracy
    weakness_threshold: float = Field(default=0.45, gt=0, lt=1)  # observed accuracy
    reassessment_pass: float = Field(default=0.8, gt=0, le=1)  # "completed" a skill
    improvement_margin: float = Field(default=0.15, gt=0, lt=1)  # counts as improved
    revision_after_days: int = Field(default=7, ge=1)  # first revision; later ones double
    mixed_practice_length: int = Field(default=8, ge=3, le=30)
    # v3 personalization (docs/modules/tutor.md, "Personalization rules")
    model_agree_threshold: float = Field(default=0.6, gt=0, lt=1)  # model must not disagree
    mastery_streak: int = Field(default=3, ge=1, le=10)  # last N answers correct ...
    mastery_window: int = Field(default=8, ge=2, le=20)  # ... and >= mastery_rate of the last W
    mastery_rate: float = Field(default=0.8, gt=0, le=1)
    mastery_min_attempts: int = Field(default=5, ge=1, le=30)
    stuck_min_attempts: int = Field(default=10, ge=3, le=50)
    stuck_recent_rate: float = Field(default=0.5, gt=0, lt=1)
    early_stop_min_answers: int = Field(default=5, ge=2, le=20)
    review_max_skills: int = Field(default=4, ge=1, le=10)
    recommendations_stale_hours: float = Field(default=6, gt=0)
    pace_window: int = Field(default=20, ge=5, le=100)
    pace_dismiss_days: int = Field(default=14, ge=1, le=90)

    # --- AI tutor explanations (OpenRouter, OpenAI-compatible chat API) ---
    # Empty key = the feature is switched off and the buttons are hidden.
    openrouter_api_key: str = ""
    ai_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    # Free models are often rate-limited upstream; these are tried in order when the main
    # model is busy or returns nothing. Comma-separated; empty = no fallback.
    ai_fallback_models: str = (
        "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,openrouter/free"
    )
    ai_base_url: str = "https://openrouter.ai/api/v1"
    # Total time budget for one AI request across every model tried (stays well under the
    # 120 s proxy limit). Each attempt reads for at most 25 s.
    ai_total_seconds: float = Field(default=50, gt=5, le=90)
    ai_daily_limit: int = Field(default=40, ge=0)  # new AI texts one student may request per day

    @field_validator("openrouter_api_key")
    @classmethod
    def clean_api_key(cls, v: str) -> str:
        """Dashboards and .env files often add quotes, spaces, a "Bearer " prefix or the whole
        .env line ("OPENROUTER_API_KEY=sk-or-...")."""
        v = re.sub(r"^(export\s+)?OPENROUTER_API_KEY\s*=\s*", "", (v or "").strip(), flags=re.I)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1].strip()
        if v.lower().startswith("bearer "):
            v = v[7:].strip()
        return v

    @property
    def kt_subject_dirs(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in self.kt_subjects.split(","):
            code, _, path = part.partition("=")
            if code.strip() and path.strip():
                out[code.strip().upper()] = path.strip()
        out.setdefault("MATH", self.kt_artifacts_dir)
        return out

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    @property
    def ai_models(self) -> list[str]:
        extra = [m.strip() for m in self.ai_fallback_models.split(",") if m.strip()]
        return list(dict.fromkeys([self.ai_model.strip(), *extra]))

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
