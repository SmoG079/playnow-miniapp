"""Generate WeChat share assets for an existing public activity."""
import base64
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.core.rate_limit import check_rate_limit
from app.core.logger import get_logger
from app.models.models import MatchPost, Tournament
from app.services.wechat_access import get_wx_access_token

router = APIRouter(prefix="/sharing", tags=["sharing"])
logger = get_logger(__name__)
Kind = Literal["post", "tournament"]
Asset = Literal["code", "link"]


async def wechat_asset(kind: str, ident: int, asset: str) -> dict:
    version = get_settings().WX_SHARE_ENV_VERSION
    token = await get_wx_access_token()
    page = f"pages/common/{kind}-detail"
    endpoint = "getwxacodeunlimit" if asset == "code" else "generate_urllink"
    payload = ({"scene": str(ident), "page": page, "env_version": version, "check_path": version == "release", "width": 430}
               if asset == "code" else {"path": page, "query": f"id={ident}", "env_version": version,
                                        "is_expire": True, "expire_type": 1, "expire_interval": 30})
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"https://api.weixin.qq.com/wxa/{endpoint}",
                                         params={"access_token": token}, json=payload)
        response.raise_for_status()
        if asset == "code" and response.content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            mime = "image/png" if response.content.startswith(b"\x89PNG") else "image/jpeg"
            return {"image_base64": base64.b64encode(response.content).decode(), "mime_type": mime}
        data = response.json()
        if asset == "link" and not data.get("errcode") and str(data.get("url_link", "")).startswith("https://wxaurl.cn/"):
            return {"url": data["url_link"]}
        if data.get("errcode") == 85079:
            raise HTTPException(503, "小程序尚无正式发布版本，微信暂不支持生成分享链接，请使用小程序内转发")
        if data.get("errcode") == 41030:
            raise HTTPException(503, "分享页面尚未发布，请配置匹配的体验版或发布小程序")
        logger.warning("WeChat share asset failed: kind=%s id=%s asset=%s code=%s", kind, ident, asset, data.get("errcode"))
    except (httpx.HTTPError, ValueError):
        # HTTP exception strings contain the access-token query: never log them.
        logger.warning("WeChat share transport failed: kind=%s id=%s asset=%s", kind, ident, asset)
    raise HTTPException(502, "微信分享资源生成失败，请稍后重试")


@router.get("/{kind}/{ident}/{asset}")
async def share_asset(kind: Kind, ident: int, asset: Asset, request: Request, db: AsyncSession = Depends(get_db)):
    import json
    activity = await db.get(MatchPost if kind == "post" else Tournament, ident)
    if not activity:
        raise HTTPException(404, "活动不存在")
    state = getattr(activity.status, "value", activity.status)
    if state == "draft":
        raise HTTPException(400, "活动发布后才能分享")
    await check_rate_limit("sharing:ip:" + (request.client.host if request.client else "unknown"), 30, 60)
    cache = get_redis_client()
    key = f"sharing:v2:{get_settings().WX_SHARE_ENV_VERSION}:{kind}:{ident}:{asset}"
    cached = await cache.get(key)
    if cached:
        return json.loads(cached)
    # Bound quota consumption across workers and repeated failures.
    await check_rate_limit(key + ":generation", 3, 300)
    if not await cache.set(key + ":lock", "1", nx=True, ex=30):
        raise HTTPException(429, "正在生成分享资源，请稍后重试")
    try:
        result = await wechat_asset(kind, ident, asset)
        await cache.setex(key, 86400, json.dumps(result))
        return result
    finally:
        await cache.delete(key + ":lock")
