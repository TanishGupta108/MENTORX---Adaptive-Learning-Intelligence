"""Application settings, loaded from environment variables (and a local .env file)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MENTORX API"
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://mentorx:mentorx@localhost:5432/mentorx"

    # Comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
