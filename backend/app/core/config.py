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
    MEDICATION_MISSED_ALERT_MAX_AGE_S: int = 21600  # a dose found missed after more than 6 h (e.g. server was down) is marked, not alerted

    # Task 3.4: wellness check (FR-D4). Check times are local clock times in this time zone.
    WELLNESS_TIMEZONE: str = "Asia/Karachi"
    WELLNESS_MAX_WINDOWS: int = 3  # active checks per Dependent (SRS: "up to three per day")
    WELLNESS_ACTIVITY_WINDOW_S: int = 1800  # "recent device activity" = a location fix in the last 30 minutes
    ESCALATION_PRIMARY_TIMEOUT_S: int = 300  # Task 3.5: Primary has 5 min to open the alert before the Secondaries are told
    ESCALATION_SECONDARY_TIMEOUT_S: int = 300  # then Secondaries have 5 more min before the external contact
    SMS_PROVIDER: str = "mock"  # Task 3.8: a real gateway is one new class in sms_service.py
    SMS_MAX_ATTEMPTS: int = 3  # tries for one external-contact SMS
    SMS_RETRY_S: int = 60  # wait between tries
    VOICE_STORAGE_DIR: str = ""  # Task 4.3: where voice audio is saved. Empty = ~/humsafar_uploads/voice (outside the repo, so audio is never committed). Cloud storage = one new class in storage_service.py
    VOICE_MAX_BYTES: int = 2_000_000  # about 2 MB
    VOICE_MAX_S: int = 120  # longest voice message
    CALL_PROVIDER: str = "mock"  # Task 4.4: 'mock' or 'zego' (ZegoCloud, clarification 75). 'zego' needs the two keys below, set only in .env
    ZEGO_APP_ID: int = 0  # from the ZegoCloud console (a number)
    ZEGO_SERVER_SECRET: str = ""  # from the ZegoCloud console (32 characters). NEVER commit it or send it to the app.
    CALL_RING_S: int = 30  # an unanswered call becomes 'missed' after this
    CALL_MAX_S: int = 3600  # a call still open after this is ended by the server
    CALL_TOKEN_TTL_S: int = 3600  # how long a join token works
    ALARM_DEFAULT_S: int = 60  # Task 3.7: how long the Dependent's phone sounds the alarm unless told otherwise
    ALARM_MIN_S: int = 10
    ALARM_MAX_S: int = 300
    # Task 5.1: medical vault (FR-G1, G3), appointments (FR-G4).
    RECORDS_STORAGE_DIR: str = ""  # where record files are saved (encrypted). Empty = ~/humsafar_uploads/records (outside the repo)
    RECORDS_ENCRYPTION_KEY: str = ""  # secret for encrypting record files (FR-N2). Empty = derived from JWT_SECRET_KEY (development only). Set it in .env for real use and never change it later
    RECORD_MAX_BYTES: int = 10_000_000  # about 10 MB per file
    RECORDS_MAX_PER_DEPENDENT: int = 500
    EXPORT_MAX_RECORDS: int = 200  # one PDF export never holds more records than this
    EXPORT_MAX_BYTES: int = 60_000_000  # files added to one PDF export, in total; later files are left out with a note
    PUBLIC_BASE_URL: str = ""  # e.g. https://api.example.com. Empty = doctor links are returned as a path only
    SHARE_DEFAULT_HOURS: int = 72  # FR-G3 recommended default
    SHARE_MAX_HOURS: int = 720  # longest a doctor link may live (30 days)
    SHARE_MAX_ACTIVE: int = 10  # open links per Dependent at one time
    VITALS_MAX_PER_DEPENDENT: int = 10_000  # typed-in readings per Dependent (Task 5.3)
    VITALS_MAX_BACKDATE_DAYS: int = 365
    EXPORT_MAX_VITALS: int = 1000  # newest readings in one PDF
    APPOINTMENT_TIMEZONE: str = "Asia/Karachi"  # the time shown in reminders
    APPOINTMENT_REMIND_LEADS_S: str = "86400,3600"  # reminders this long before: 24 h and 1 h (comma separated)
    APPOINTMENT_MAX_OPEN: int = 100  # scheduled appointments per Dependent
    WELLNESS_ALERT_MAX_AGE_S: int = 21600  # a check found unanswered more than 6 h after its deadline is closed, not alerted

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
