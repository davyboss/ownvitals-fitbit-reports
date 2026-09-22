from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_locale: Literal["en", "ru"] = "en"
    google_health_client_secrets: Path = Path("data/google-client-secret.json")
    google_health_token_path: Path = Path("data/google-health-token.json")
    google_health_scopes: str = (
        "activity_and_fitness,health_metrics_and_measurements,sleep,profile"
    )
    telegram_bot_token: str
    telegram_allowed_chat_id: int
    database_url: str = "sqlite:///data/app.db"
    raw_data_dir: Path = Path("data/raw-google-health")
    food_photo_dir: Path = Path("data/food-photos")
    fatsecret_report_dir: Path = Path("data/fatsecret-reports")
    fatsecret_consumer_key: str | None = None
    fatsecret_consumer_secret: str | None = None
    fatsecret_auto_import_time: str = "23:30"
    log_dir: Path = Path("logs")
    backup_dir: Path = Path("data/backups")
    obsidian_vault: Path = Path("obsidian-vault")
    timezone: str = "Europe/Kiev"
    # Legacy fallback used by older .env files and tests.
    claude_model: str = "sonnet"
    claude_max_turns: int = 1
    claude_input_price_per_million_usd: float = 2.0
    claude_output_price_per_million_usd: float = 10.0
    claude_cache_read_price_per_million_usd: float = 0.20
    claude_cache_creation_price_per_million_usd: float = 2.50
    claude_report_model: str = "claude-opus-5"
    claude_question_model: str = "claude-sonnet-5"
    claude_report_input_price_per_million_usd: float = 5.0
    claude_report_output_price_per_million_usd: float = 25.0
    claude_report_cache_read_price_per_million_usd: float = 0.50
    claude_report_cache_creation_price_per_million_usd: float = 6.25
    claude_question_input_price_per_million_usd: float = 2.0
    claude_question_output_price_per_million_usd: float = 10.0
    claude_question_cache_read_price_per_million_usd: float = 0.20
    claude_question_cache_creation_price_per_million_usd: float = 2.50
    sync_interval_minutes: int = 240
    daily_report_time: str = "08:00"
    weekly_report_time: str = "08:15"
    monthly_report_time: str = "08:30"
    backup_time: str = "03:00"
    weekly_report_weekday: int = 0
    scheduler_tick_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def google_health_scope_urls(self) -> list[str]:
        allowed = {
            "activity_and_fitness",
            "health_metrics_and_measurements",
            "sleep",
            "profile",
        }
        names = [item.strip() for item in self.google_health_scopes.split(",") if item.strip()]
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValueError(f"unknown Google Health scope(s): {', '.join(unknown)}")
        return [
            f"https://www.googleapis.com/auth/googlehealth.{name}.readonly"
            for name in names
        ]


def load_settings() -> Settings:
    return Settings()
