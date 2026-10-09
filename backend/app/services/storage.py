"""媒体资源存储封装（腾讯云 COS，未配置时回退本地磁盘）。

配置与注意事项见 docs/cos-media-storage.md。

设计取舍：COS 密钥未配置时**回退本地磁盘**而非直接报错。
- 生产应配置 `OSS_ACCESS_KEY_ID/SECRET/BUCKET_NAME`，实际后端取决于配置；认证材料另需独立私有桶；
- CI（项目惯例不注入云凭证）与本地开发无需密钥即可跑通上传链路，
  `tests/http_fullflow.py` 会真实 GET 返回的 URL 并比对字节，回退后依然成立；
- 回退时每次上传都打 WARNING，避免生产密钥失效后被静默降级而无人察觉。
"""

import os
import uuid
from typing import Optional

from qcloud_cos import CosConfig, CosS3Client

from app.core.config import get_settings
from app.core.logger import get_logger

settings = get_settings()
logger = get_logger(__name__)

# 扩展名 -> MIME。不直接信任客户端上传的 content_type。
MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".pdf": "application/pdf",
}

# 对象前缀白名单，见 docs/cos-media-storage.md
# doc/ 仅走私有上传；已公开的旧 COS 对象需另行迁移并撤销公读权限。
PREFIXES = {"avatar", "court", "post", "video", "doc", "upload"}

# 回退目录，同时也是 /uploads 静态挂载的根目录（main.py 复用此常量，避免两处路径不一致）
LOCAL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
)

PRIVATE_LOCAL_DIR = os.path.join(os.path.dirname(LOCAL_DIR), "private_uploads")

_client: Optional[CosS3Client] = None


class StorageUnavailable(RuntimeError):
    """Activity media must never silently become local server files."""


def is_configured() -> bool:
    """COS 密钥是否齐备。缺任一项即视为未配置，走本地磁盘回退。"""
    return bool(
        settings.OSS_ACCESS_KEY_ID
        and settings.OSS_ACCESS_KEY_SECRET
        and settings.OSS_BUCKET_NAME
    )


def _get_client() -> CosS3Client:
    """惰性创建全局复用的 COS 客户端。"""
    global _client
    if _client is None:
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


def active_backend() -> str:
    """当前生效的存储后端，供日志与排障使用。"""
    return "cos" if is_configured() else "local"


def build_key(prefix: str, ext: str) -> str:
    """生成对象 key，形如 court/9f2a....jpg。前缀不在白名单内回落 upload/。"""
    safe = prefix if prefix in PREFIXES else "upload"
    return f"{safe}/{uuid.uuid4().hex}{ext.lower()}"


def public_url(key: str) -> str:
    """桶为公有读，直接拼默认域名即可访问。"""
    return (
        f"https://{settings.OSS_BUCKET_NAME}.cos.{settings.COS_REGION}.myqcloud.com/{key}"
    )


def _local_path(key: str) -> str:
    """把对象 key 映射到本地文件路径，并阻断越界写入。"""
    path = os.path.abspath(os.path.join(LOCAL_DIR, key))
    if not path.startswith(LOCAL_DIR + os.sep):
        raise ValueError(f"非法对象 key: {key!r}")
    return path


def put_object(key: str, content: bytes, ext: str = "") -> str:
    """上传对象并返回 URL；活动图片强制 COS，其余类型兼容本地回退。"""
    if key.startswith("doc/"):
        raise StorageUnavailable("认证材料必须通过私有上传接口")
    if not is_configured():
        if key.startswith("post/"):
            raise StorageUnavailable("活动图片存储暂不可用，请稍后重试")
        logger.warning(
            "COS 未配置，上传落本地磁盘（非生产预期）：key=%s 目录=%s",
            key,
            LOCAL_DIR,
        )
        path = _local_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return f"{settings.PUBLIC_BASE_URL}/uploads/{key}"

    _get_client().put_object(
        Bucket=settings.OSS_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=MIME.get(ext.lower(), "application/octet-stream"),
    )
    return public_url(key)



def put_private_document(filename, content, ext):
    key = f"doc/{filename}"
    if is_configured():
        if not settings.COS_PRIVATE_BUCKET_NAME or settings.COS_PRIVATE_BUCKET_NAME == settings.OSS_BUCKET_NAME:
            raise StorageUnavailable("认证材料需配置独立私有 COS 桶")
        _get_client().put_object(Bucket=settings.COS_PRIVATE_BUCKET_NAME, Key=key, Body=content,
            ACL="private", ContentType=MIME[ext])
        return "cos"
    os.makedirs(PRIVATE_LOCAL_DIR, mode=0o700, exist_ok=True)
    descriptor = os.open(os.path.join(PRIVATE_LOCAL_DIR, filename), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as f:
        f.write(content)
    return "local"


def read_private_document(filename):
    stream = _get_client().get_object(Bucket=settings.COS_PRIVATE_BUCKET_NAME,
        Key=f"doc/{filename}")["Body"].get_raw_stream()
    try:
        return stream.read()
    finally:
        stream.close()


def delete_object(key: str) -> None:
    """删除对象（桶开启版本控制，删除可通过历史版本恢复）。"""
    if not is_configured():
        logger.warning("COS 未配置，删除本地文件：key=%s", key)
        try:
            os.remove(_local_path(key))
        except FileNotFoundError:
            pass
        return

    _get_client().delete_object(Bucket=settings.OSS_BUCKET_NAME, Key=key)
