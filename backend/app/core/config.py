from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Club MiniApp API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "mysql+aiomysql://root:password@mysql:3306/club_db"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production-use-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # WeChat
    WX_APP_ID: str = ""
    WX_APP_SECRET: str = ""
    WX_MCH_ID: str = ""
    WX_MCH_API_V3_KEY: str = ""
    WX_MCH_SERIAL_NO: str = ""
    WX_MCH_PRIVATE_KEY_PATH: str = "/app/certs/apiclient_key.pem"
    WX_PAY_NOTIFY_URL: str = "https://www.tennisplaynow.site/api/v1/bookings/wx-notify"

    # OSS
    OSS_ENDPOINT: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""

    # Booking
    BOOKING_LOCK_TTL_SECONDS: int = 600  # 10 min payment window
    FREE_CANCEL_HOURS: int = 2  # free cancel before 2h

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
