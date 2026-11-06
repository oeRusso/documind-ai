"""Application settings, read only from environment variables (and the repo's .env in dev)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[3] is the repository root, where .env lives.
# Inside the container that path does not exist and pydantic-settings simply skips it.
_REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

# 32 characters is 256 bits when the secret is hex (`openssl rand -hex 32` gives 64).
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DocuMind AI"
    app_env: Literal["development", "test", "production"] = "development"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    database_url: PostgresDsn
    database_migration_url: PostgresDsn

    # --- Authentication (stage 2, see ADR 0004) ---
    # SecretStr hides the value in logs and tracebacks; read it with .get_secret_value().
    jwt_secret: SecretStr = Field(min_length=JWT_SECRET_MIN_LENGTH)
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=90)
    # Origin of the web app (scheme://host[:port]). Cookie endpoints reject any other Origin (CSRF).
    app_origin: str = "http://localhost:3000"

    @field_validator("app_origin")
    @classmethod
    def _validate_origin(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("must look like https://app.example.com")
        if parts.path not in {"", "/"} or parts.query or parts.fragment:
            raise ValueError("must be an origin only: no path, query or fragment")
        # Browsers send Origin without a trailing slash; normalize so a plain == works.
        return f"{parts.scheme}://{parts.netloc}".lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
