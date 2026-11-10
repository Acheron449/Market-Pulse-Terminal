"""Settings defaults and environment overrides (AGENTS.md §3)."""

from pytest import MonkeyPatch

from app.core.config import Settings


def test_defaults_are_safe_for_development() -> None:
    settings = Settings(_env_file=None)  # ignore the developer's .env

    assert settings.app_name == "Market Pulse Terminal"
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"


def test_environment_overrides_defaults(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
