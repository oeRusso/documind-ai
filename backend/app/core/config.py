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
        # `RAG_MIN_SCORE=` (empty, as in an old .env) means "use the default", not "".
        env_ignore_empty=True,
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

    # --- Attempt limits (stage 2, ADR 0005). Per IP until stage 3 trusts CF-Connecting-IP. ---
    login_limit_per_ip_per_minute: int = Field(default=20, ge=1)
    login_limit_per_email_per_15_minutes: int = Field(default=10, ge=1)
    register_limit_per_ip_per_hour: int = Field(default=10, ge=1)
    accept_invitation_limit_per_user_per_minute: int = Field(default=10, ge=1)

    # --- Email (stage 2: invitations) ---
    # Without SMTP_HOST nothing is sent (only logged): the invitation link is still shown to
    # whoever invites. In development SMTP_HOST=mailpit (see compose.yaml).
    smtp_host: str | None = None
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    mail_from: str = "DocuMind AI <no-reply@documind.local>"

    # --- Documents (stage 4) ---
    # Where uploaded files live: /{organization_id}/{random uuid}. A volume in compose.
    storage_path: Path = Path("/data/documents")
    max_upload_mb: int = Field(default=25, ge=1, le=95)  # Cloudflare (free) cuts at 100 MB
    max_upload_pages: int = Field(default=500, ge=1)
    # A deleted document keeps its files this long, so restoring a recent backup still works.
    document_purge_days: int = Field(default=30, ge=0)

    # --- Processing queue (stage 5): Valkey speaks the Redis protocol, hence redis:// ---
    # Without it the API still works, but documents stay "pending" (nothing processes them).
    celery_broker_url: str | None = None

    # --- Local AI with Ollama (stage 6) ---
    # Without it, documents are processed without embeddings and search uses words only.
    ollama_url: str | None = None
    embedding_model: str = "bge-m3"  # one of app/ai/providers/embeddings.py KNOWN_MODELS

    # --- Answers with citations (stage 7, ADR 0009) ---
    # The language model that writes answers. Small (1-3B, quantized): the VPS is shared.
    llm_model: str = "llama3.2:3b"
    # How long Ollama keeps the model in RAM after the last answer (loading it takes seconds).
    llm_keep_alive: str = "30m"
    # Answers generated at the same time; the rest wait in line (CPU only, shared RAM).
    llm_max_concurrency: int = Field(default=1, ge=1, le=4)
    # Below this meaning similarity (cosine, 0..1) of the best chunk: "no encontré evidencia",
    # without calling the LLM. Chosen with the unanswerable questions of the dataset.
    rag_min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    # Size of the context given to the model (small models answer better with short contexts).
    rag_context_tokens: int = Field(default=1500, ge=200, le=6000)
    rag_max_answer_tokens: int = Field(default=512, ge=64, le=2048)
    chat_limit_per_user_per_minute: int = Field(default=10, ge=1)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @field_validator(
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "celery_broker_url",
        "ollama_url",
        mode="before",
    )
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        # `SMTP_HOST=` (as in .env.example) means "not configured", not a host named "".
        return None if isinstance(value, str) and value.strip() == "" else value

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
