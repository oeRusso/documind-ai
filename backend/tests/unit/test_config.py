import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB_URL = "postgresql+asyncpg://user:pw@localhost:5432/db"  # pragma: allowlist secret
GOOD_SECRET = "x" * 64


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": DB_URL,
        "database_migration_url": DB_URL,
        "jwt_secret": GOOD_SECRET,
        **overrides,
    }
    # _env_file=None: ignore the developer's .env so the test only sees these values.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_auth_defaults() -> None:
    settings = make_settings()
    assert settings.access_token_minutes == 15
    assert settings.refresh_token_days == 14
    assert settings.app_origin == "http://localhost:3000"


def test_jwt_secret_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None, database_url=DB_URL, database_migration_url=DB_URL)


def test_short_jwt_secret_is_rejected() -> None:
    # The placeholder from .env.example must never be accepted.
    with pytest.raises(ValidationError, match="jwt_secret"):
        make_settings(jwt_secret="change-me-64-random-characters")  # pragma: allowlist secret


def test_jwt_secret_is_hidden_in_repr() -> None:
    settings = make_settings()
    assert GOOD_SECRET not in repr(settings)
    assert settings.jwt_secret.get_secret_value() == GOOD_SECRET


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:3000", "http://localhost:3000"),
        ("https://App.Example.com/", "https://app.example.com"),
    ],
)
def test_app_origin_is_normalized(raw: str, expected: str) -> None:
    assert make_settings(app_origin=raw).app_origin == expected


@pytest.mark.parametrize(
    "raw",
    ["localhost:3000", "ftp://example.com", "https://example.com/app", "https://example.com/?a=1"],
)
def test_app_origin_rejects_non_origins(raw: str) -> None:
    with pytest.raises(ValidationError, match="app_origin"):
        make_settings(app_origin=raw)


@pytest.mark.parametrize(
    ("field", "value"), [("access_token_minutes", 0), ("refresh_token_days", 91)]
)
def test_token_lifetimes_have_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match=field):
        make_settings(**{field: value})


def test_empty_smtp_values_mean_not_configured(offline_settings: Settings) -> None:
    settings = Settings.model_validate(
        {
            **offline_settings.model_dump(),
            "jwt_secret": offline_settings.jwt_secret.get_secret_value(),
            "smtp_host": "",
            "smtp_password": " ",
        }
    )

    assert settings.smtp_host is None
    assert settings.smtp_password is None
