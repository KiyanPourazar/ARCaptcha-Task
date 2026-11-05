from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_username: str = "demo"
    bot_password: str = "demo"
    target_url: str = "https://demo.arcaptcha.co"
    database_url: str = "sqlite:////data/runs.db"
    selenium_remote_url: str | None = None
    chrome_binary: str | None = None

    page_load_timeout: int = 45
    captcha_wait_timeout: int = 30
    login_wait_timeout: int = 20

    bot_stealth: bool = True
    humanize_delays: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
