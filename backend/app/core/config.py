from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Club MiniApp API"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "mysql+asyncmy://club_user:club_pass@101.34.213.125:3306/club_db"

    # Redis
    REDIS_URL: str = "redis://:redis_pass@101.34.213.125:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "generate-a-random-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

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
    # 微信支付公钥（抖音式「平台证书」已被微信下线，2024-10 起新商户只能申请
    # 微信支付公钥）。两者都配置时才启用公钥模式：SDK 不再尝试下载平台证书，
    # 回调验签改用该公钥。见 https://pay.weixin.qq.com/doc/v3/merchant/4012153196
    WX_PAY_PUBLIC_KEY_PATH: str = ""
    WX_PAY_PUBLIC_KEY_ID: str = ""
    # 真实订场支付总开关。false 时 POST /bookings/{id}/pay 走占位确认
    # （直接标 paid 且无任何真实交易，等于免费订场），仅供本地/CI 使用。
    # 生产必须为 true；启动日志会打印实际状态。
    WX_PAY_ENABLED: bool = False
    # 微信支付账单里展示的商品描述
    WX_PAY_DESCRIPTION: str = "网球场地预订"

    
    # Tencent Cloud COS — 媒体资源存储，见 docs/cos-media-storage.md
    # 生产环境必须使用 CAM 子账号密钥（只授权单个桶），不要用主账号
    OSS_ENDPOINT: str = "cos.ap-shanghai.myqcloud.com"
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""
    COS_PRIVATE_BUCKET_NAME: str = ""  # Separate bucket with public access disabled for certification materials.
    COS_REGION: str = "ap-shanghai"
    # 仅当使用 STS 临时凭证时需要（永久密钥留空）
    OSS_SESSION_TOKEN: str = ""

    TOURNAMENT_PREPAY_ENABLED: bool = False
    TOURNAMENT_SEAT_TTL_SECONDS: int = 600

    # Booking
    BOOKING_LOCK_TTL_SECONDS: int = 600
    PREPAY_ID_TTL_SECONDS: int = 300

    # Settlement / profit-sharing
    # 自动分账执行总开关。平台用自有商户号直接收款时为 false —— 此时
    # SettlementRecord 仅作记账留存，不会向微信发起分账请求。
    PROFIT_SHARING_ENABLED: bool = False
    SETTLEMENT_DELAY_DAYS: int = 30
    SETTLEMENT_MAX_RETRIES: int = 3
    SETTLEMENT_BATCH_SIZE: int = 100
    SETTLEMENT_PLATFORM_ACCOUNT: str = ""  # platform mch_id or openid

    # Refund retry
    REFUND_MAX_RETRIES: int = 5
    REFUND_RETRY_BACKOFF_BASE_SECONDS: int = 30
    REFUND_POLL_INTERVAL_MINUTES: int = 5
    REFUND_BATCH_SIZE: int = 50

    # Tencent Map (optional: address/city resolution and current city weather)
    TENCENT_MAP_KEY: str = ""
    TENCENT_MAP_SK: str = ""

    # Public asset base URL — clients load uploaded images from this host.
    # MUST be https and the same origin/port nginx exposes for /uploads.
    PUBLIC_BASE_URL: str = "https://www.tennisplaynow.site:8443"
    UPLOAD_MAX_MB: int = 5
    UPLOAD_ALLOWED_EXT: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".gif")

    # Logging
    LOG_LEVEL: str = "DEBUG"
    LOG_MYSQL_LEVEL: str = "WARNING"   # INFO=显示SQL语句, WARNING=关闭
    LOG_DIR: str = "logs"
    LOG_BACKUP_DAYS: int = 10           # info/error 日志保留天数
    LOG_MAX_BYTES: int = 20_971_520     # 20 MB — debug/mysql 大小轮转阈值
    LOG_BACKUP_COUNT: int = 20          # debug/mysql 保留文件数

    # Rate limiting (per-minute limits for sensitive booking endpoints)
    RATE_LIMIT_PAY_PER_MINUTE: int = 10
    # 主动查单比下单频繁得多（支付结果页会轮询），因此单独给一个更宽的上限。
    RATE_LIMIT_SYNC_PAY_PER_MINUTE: int = 30
    RATE_LIMIT_BOOKING_PER_MINUTE: int = 10
    RATE_LIMIT_CANCEL_PER_MINUTE: int = 10
    RATE_LIMIT_REFUND_PER_MINUTE: int = 5
    # 主动查退款：与查支付同理，属于只读轮询，单独给一个更宽的上限。
    RATE_LIMIT_SYNC_REFUND_PER_MINUTE: int = 30

    @model_validator(mode="after")
    def require_production_secret(self):
        if not self.DEBUG and (self.JWT_SECRET_KEY.startswith("generate-a-random-secret-key-here") or len(self.JWT_SECRET_KEY) < 32):
            raise ValueError("生产 JWT_SECRET_KEY 必须显式配置为至少 32 字符的独立随机密钥")
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
