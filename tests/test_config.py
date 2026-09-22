from pathlib import Path

import pytest

from fitbit_report.config import load_settings


@pytest.fixture(autouse=True)
def required_settings_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRETS", str(tmp_path / "client-secret.json"))
    monkeypatch.setenv("GOOGLE_HEALTH_TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "42")


def test_load_settings_reads_required_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRETS", str(tmp_path / "client-secret.json"))
    monkeypatch.setenv("GOOGLE_HEALTH_TOKEN_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_ID", "42")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("TIMEZONE", "Europe/Kiev")
    monkeypatch.setenv("APP_LOCALE", "en")

    settings = load_settings()

    assert settings.telegram_allowed_chat_id == 42
    assert settings.timezone == "Europe/Kiev"
    assert settings.claude_model == "sonnet"
    assert settings.app_locale == "en"
    assert settings.food_photo_dir == Path("data/food-photos")


def test_google_health_settings_build_readonly_scope_urls(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_HEALTH_SCOPES",
        "activity_and_fitness,health_metrics_and_measurements,sleep,profile",
    )

    settings = load_settings()

    assert settings.google_health_scope_urls() == [
        "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
        "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
        "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
        "https://www.googleapis.com/auth/googlehealth.profile.readonly",
    ]


def test_google_health_settings_reject_unknown_scope(monkeypatch):
    monkeypatch.setenv("GOOGLE_HEALTH_SCOPES", "activity_and_fitness,unknown")

    settings = load_settings()

    with pytest.raises(ValueError, match="unknown"):
        settings.google_health_scope_urls()
