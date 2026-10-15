import httpx
from fastapi import HTTPException
from app.core.config import get_settings

settings = get_settings()


async def get_wx_access_token():
    """Get cached mini-program access token, or fetch a new one."""
    if not settings.WX_APP_ID or not settings.WX_APP_SECRET:
        raise HTTPException(503, "微信能力暂未配置")
    import redis.asyncio as redis
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = f"wx:access_token:{settings.WX_APP_ID}"
        token = await r.get(key)
        if token:
            return token
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": settings.WX_APP_ID,
                    "secret": settings.WX_APP_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        token = data.get("access_token")
        if not token:
            raise HTTPException(502, "微信凭据获取失败，请稍后重试")
        expires = data.get("expires_in", 7200)
        await r.setex(key, expires - 60, token)
        return token
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "微信服务暂时不可用，请稍后重试") from None
    finally:
        await r.close()
