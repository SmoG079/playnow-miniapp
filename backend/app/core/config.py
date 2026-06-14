from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Club MiniApp API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "mysql+asyncmy://club_user:club_pass@mysql:3306/club_db"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "generate-a-random-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # WeChat Mini Program
    WX_APP_ID: str = ""
    WX_APP_SECRET: str = ""

    # WeChat Pay V3
    WX_MCH_ID: str = ""
    WX_MCH_API_V3_KEY: str = ""
    WX_MCH_SERIAL_NO: str = ""
    WX_MCH_PRIVATE_KEY_PATH: str = ""
    WX_PAY_NOTIFY_URL: str = ""
    WX_PAY_CERT_DIR: str = "/app/certs"
    
    # OSS
    OSS_ENDPOINT: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""

    # Booking
    BOOKING_LOCK_TTL_SECONDS: int = 600
    PREPAY_ID_TTL_SECONDS: int = 300
    FREE_CANCEL_HOURS: int = 24

    # Settlement / profit-sharing
    SETTLEMENT_DELAY_DAYS: int = 30
    SETTLEMENT_MAX_RETRIES: int = 3
    SETTLEMENT_BATCH_SIZE: int = 100
    SETTLEMENT_PLATFORM_ACCOUNT: str = ""  # platform mch_id or openid

    # Refund retry
    REFUND_MAX_RETRIES: int = 5
    REFUND_RETRY_BACKOFF_BASE_SECONDS: int = 30
    REFUND_POLL_INTERVAL_MINUTES: int = 5
    REFUND_BATCH_SIZE: int = 50

    # Rate limiting (per-minute limits for sensitive booking endpoints)
    RATE_LIMIT_PAY_PER_MINUTE: int = 10
    RATE_LIMIT_CANCEL_PER_MINUTE: int = 10
    RATE_LIMIT_REFUND_PER_MINUTE: int = 5


@lru_cache()
def get_settings() -> Settings:
    return Settings()
