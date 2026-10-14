"""
Central application configuration.

Reads from environment variables / .env file. No hardcoded secrets.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-.env"


class Settings(BaseSettings):
    # General
    APP_NAME: str = "Humsafar API"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/humsafar_dev"

    # JWT (Task 1.3). SDS 11.3: short-lived access tokens (~15 min) paired with
    # longer-lived refresh tokens.
    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # KYC (Task 1.4). Only the mock provider exists until a real vendor is chosen (SDS 3.3).
    KYC_PROVIDER: str = "mock"
    MOCK_OTP_CODE: str = "123456"  # the fixed code the mock accepts; never used by a real provider

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _require_real_secret_outside_development(self) -> "Settings":
        # Never let the placeholder secret reach staging/production.
        if self.ENVIRONMENT != "development" and self.JWT_SECRET_KEY == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set to a real secret outside development.")
        if self.KYC_PROVIDER != "mock":
            raise ValueError("KYC_PROVIDER must be 'mock'; no real provider is integrated yet.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — avoids re-reading .env on every import."""
    return Settings()
