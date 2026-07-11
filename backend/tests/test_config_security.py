from urllib.parse import urlsplit

from app.config import Settings


def test_default_database_url_has_no_embedded_credentials() -> None:
    default_url = Settings.model_fields["database_url"].default

    assert isinstance(default_url, str)

    parsed = urlsplit(
        default_url.replace(
            "postgresql+asyncpg://",
            "postgresql://",
            1,
        )
    )

    assert parsed.username is None
    assert parsed.password is None


def test_environment_can_supply_database_url(monkeypatch) -> None:
    secure_url = (
        "postgresql+asyncpg://runtime_user:"
        "runtime_secret@database:5432/superagent"
    )
    monkeypatch.setenv("DATABASE_URL", secure_url)

    settings = Settings(_env_file=None)

    assert settings.database_url == secure_url