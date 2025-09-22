"""Application configuration utilities."""
from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Runtime settings loaded from the environment."""

    bybit_api_key: str = Field(env="BYBIT_API_KEY", default="")
    bybit_api_secret: str = Field(env="BYBIT_API_SECRET", default="")
    bybit_base_url: str = Field(
        env="BYBIT_BASE_URL",
        default="https://api.bybit.com",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
