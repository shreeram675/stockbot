from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "Personal AI Telegram Investment Assistant"
    app_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"

    telegram_allowed_user_id: int | None = None
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_webhook_url: str | None = None

    database_url: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    dhan_client_id: str | None = None
    dhan_access_token: str | None = None
    dhan_api_key: str | None = None
    dhan_api_secret: str | None = None
    dhan_api_base_url: str = "https://api.dhan.co"
    dhan_auth_base_url: str = "https://auth.dhan.co"
    dhan_redirect_url: str = "https://stockbot-rho.vercel.app/api/dhan/callback"
    dhan_postback_url: str = "https://stockbot-rho.vercel.app/api/dhan/postback"
    dhan_daily_auth_time_ist: str = "08:30"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    news_provider: Literal["finnhub"] = "finnhub"
    finnhub_api_key: str | None = None

    yfinance_timeout_seconds: int = 15

    default_risk_profile: str = "Balanced"
    monthly_investment_budget_inr: int = 5000
    monthly_investment_day: int = 12

    enable_daily_morning_report: bool = True
    enable_daily_close_report: bool = True
    enable_weekly_report: bool = True
    enable_monthly_workflow: bool = True

    http_timeout_seconds: int = 20
    http_retry_attempts: int = 3
    cron_secret: str | None = None

    @model_validator(mode="before")
    @classmethod
    def blank_strings_to_none(cls, data):
        if not isinstance(data, dict):
            return data
        optional_blank_fields = {
            "telegram_allowed_user_id",
            "telegram_bot_token",
            "telegram_webhook_secret",
            "telegram_webhook_url",
            "database_url",
            "supabase_url",
            "supabase_service_role_key",
            "dhan_client_id",
            "dhan_access_token",
            "dhan_api_key",
            "dhan_api_secret",
            "dhan_redirect_url",
            "dhan_postback_url",
            "gemini_api_key",
            "finnhub_api_key",
            "cron_secret",
        }
        return {
            key: None if key in optional_blank_fields and value == "" else value
            for key, value in data.items()
        }

    @field_validator("default_risk_profile")
    @classmethod
    def validate_risk_profile(cls, value: str) -> str:
        allowed = {"Conservative", "Balanced", "Aggressive", "Custom"}
        normalized = value.strip().title()
        if normalized not in allowed:
            raise ValueError(f"default risk profile must be one of {sorted(allowed)}")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
