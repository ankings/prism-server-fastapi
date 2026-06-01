from functools import lru_cache
from typing import Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_name: str = "prism-server-fastapi"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    database_url: str = "mysql+aiomysql://user:password@localhost:3306/prism_dev"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    log_level: Literal["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: str = "logs/app.log"

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, v: str, info) -> str:
        app_env = (info.data or {}).get("app_env", "development")
        if app_env != "development" and v == "dev-secret-key-change-in-production":
            raise ValueError(
                "SECRET_KEY must be set to a strong random value in non-development environments. "
                "Generate one with: openssl rand -hex 32"
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level alias so `from app.config import settings` works throughout the codebase
settings = get_settings()
