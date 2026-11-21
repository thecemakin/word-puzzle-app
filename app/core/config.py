from functools import lru_cache
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_DEFAULT_JWT_SECRET = "dev-only-secret-key-do-not-use-in-production-32bytes"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Word Puzzle API"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    postgres_user: str = "wordpuzzle"
    postgres_password: str = "wordpuzzle_dev"
    postgres_db: str = "wordpuzzle"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    database_url_override: Optional[str] = None

    jwt_secret_key: str = _DEV_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_auth_requests: int = 20
    rate_limit_auth_window_seconds: int = 60

    default_ui_language: str = "tr"
    allowed_game_languages: str = "tr,en"
    allowed_turn_duration_hours: str = "12,24,48,72"
    dictionaries_dir: str = "data/dictionaries"
    timeout_check_interval_seconds: int = 60

    @field_validator("app_env", "default_ui_language")
    @classmethod
    def normalize_lower(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG must be false when APP_ENV=production")
            if (
                self.jwt_secret_key == _DEV_DEFAULT_JWT_SECRET
                or len(self.jwt_secret_key) < 32
            ):
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a strong secret (>= 32 chars) in production"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def game_languages(self) -> list[str]:
        return [
            lang.strip().lower()
            for lang in self.allowed_game_languages.split(",")
            if lang.strip()
        ]

    @property
    def turn_duration_hours_options(self) -> list[int]:
        return [
            int(hours.strip())
            for hours in self.allowed_turn_duration_hours.split(",")
            if hours.strip()
        ]

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
