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

    # Location ingestion (Task 2.1, FR-C1). Adaptive polling: the server tells the phone how long
    # to wait before the next fix. SDS 20: this is the main lever for NFR-02 (battery).
    LOCATION_INTERVAL_MOVING_S: int = 10  # while moving
    LOCATION_INTERVAL_STATIONARY_S: int = 60  # standing still
    LOCATION_INTERVAL_IDLE_S: int = 180  # standing still for a long time
    LOCATION_IDLE_AFTER_S: int = 600  # how long without moving before "idle"
    LOCATION_MOVE_THRESHOLD_M: float = 25.0  # smaller shifts are treated as GPS jitter
    LOCATION_MOVING_SPEED_MPS: float = 0.8  # about 3 km/h, a slow walk
    LOCATION_MAX_FUTURE_S: int = 300  # reject fixes stamped more than 5 min ahead of the server
    LOCATION_MAX_AGE_S: int = 86400  # reject fixes older than 24 h (offline buffering allowed up to this)
    LOCATION_STALE_AFTER_S: int = 480  # Guardian screen hint: "last fix is old"

    # Device health (Task 2.3, FR-L1 / FR-L2).
    DEVICE_LOW_BATTERY_PCT: int = 15  # SRS FR-L1: alert Guardians when the battery falls to 15%
    DEVICE_BATTERY_RECOVER_PCT: int = 20  # the alert closes only above this, so 15/16/15 does not flap
    DEVICE_BATTERY_DEPLETED_PCT: int = 5  # at or below this when contact is lost: "probably the battery died"
    DEVICE_OFFLINE_AFTER_S: int = 600  # FR-L2 configured threshold: no fix for 10 minutes = offline
    LOCATION_INTERVAL_LOW_BATTERY_S: int = 60  # while the battery is low, check in at least this often

    # Background jobs (the offline sweep now; missed doses and escalation timers in Phase 3).
    # Task 3.1: notifications. Only the mock push provider exists until Firebase is set up (Talha's 3.14).
    PUSH_PROVIDER: str = "mock"
    NOTIFY_RESOLVED_WINDOW_S: int = 86400  # "all clear" messages are sent for events resolved in the last day

    # Task 3.2: medication (FR-F1). Dose times are written in this local time zone.
    MEDICATION_TIMEZONE: str = "Asia/Karachi"
    MEDICATION_REMIND_BEFORE_S: int = 900  # standard reminder this long before the dose time
    MEDICATION_WINDOW_S: int = 1800  # a dose still unconfirmed this long after its time counts as missed (Task 3.3)
    MEDICATION_CONFIRM_TOKEN_S: int = 120  # step 2 of the confirmation must follow step 1 within this time
    MEDICATION_MAX_ACTIVE_SCHEDULES: int = 30  # per Dependent

    SCHEDULER_ENABLED: bool = True
    SCHEDULER_TICK_S: int = 60

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
