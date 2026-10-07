"""腾讯云 COS 对象存储封装。

配置与注意事项见 docs/cos-media-storage.md。

密钥未配置时 put/delete 抛出 RuntimeError，避免静默失败或误落到本地磁盘。
"""

import uuid
from typing import Optional

from qcloud_cos import CosConfig, CosS3Client

from app.core.config import get_settings

settings = get_settings()

# 扩展名 -> MIME。不直接信任客户端上传的 content_type。
MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
}

# 对象前缀白名单，见 docs/cos-media-storage.md
# doc/ 存放俱乐部认证材料等敏感文件，当前与图片同样公开可读，后续应加桶策略收紧
PREFIXES = {"avatar", "court", "post", "video", "doc", "upload"}

_client: Optional[CosS3Client] = None


def _get_client() -> CosS3Client:
    """惰性创建全局复用的 COS 客户端。"""
    global _client
    if _client is None:
        if not (
            settings.OSS_ACCESS_KEY_ID
            and settings.OSS_ACCESS_KEY_SECRET
            and settings.OSS_BUCKET_NAME
        ):
            raise RuntimeError(
                "COS 未配置：请在 .env 设置 OSS_ACCESS_KEY_ID / "
                "OSS_ACCESS_KEY_SECRET / OSS_BUCKET_NAME"
            )
        _client = CosS3Client(
            CosConfig(
                Region=settings.COS_REGION,
                SecretId=settings.OSS_ACCESS_KEY_ID,
                SecretKey=settings.OSS_ACCESS_KEY_SECRET,
                Token=settings.OSS_SESSION_TOKEN or None,
                Scheme="https",
            )
        )
    return _client


def build_key(prefix: str, ext: str) -> str:
    """生成对象 key，形如 court/9f2a....jpg。前缀不在白名单内回落 upload/。"""
    safe = prefix if prefix in PREFIXES else "upload"
    return f"{safe}/{uuid.uuid4().hex}{ext.lower()}"


def public_url(key: str) -> str:
    """桶为公有读，直接拼默认域名即可访问。"""
    return (
        f"https://{settings.OSS_BUCKET_NAME}.cos.{settings.COS_REGION}.myqcloud.com/{key}"
    )


def put_object(key: str, content: bytes, ext: str = "") -> str:
    """上传对象并返回公网可达 URL。"""
    _get_client().put_object(
        Bucket=settings.OSS_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=MIME.get(ext.lower(), "application/octet-stream"),
    )
    return public_url(key)


def delete_object(key: str) -> None:
    """删除对象（桶开启版本控制，删除可通过历史版本恢复）。"""
    _get_client().delete_object(Bucket=settings.OSS_BUCKET_NAME, Key=key)
