import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.api.deps import get_current_user
from app.models.models import User
from app.schemas.schemas import WxLoginRequest, TokenResponse, RefreshRequest, PhoneRequest

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


async def _get_wx_access_token():
    """Get cached mini-program access token, or fetch a new one."""
    import redis.asyncio as redis
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = "wx:access_token"
        token = await r.get(key)
        if token:
            return token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": settings.WX_APP_ID,
                    "secret": settings.WX_APP_SECRET,
                },
            )
            data = resp.json()
        token = data.get("access_token")
        if not token:
            raise HTTPException(status_code=500, detail=f"WeChat token failed: {data.get('errmsg', 'unknown')}")
        expires = data.get("expires_in", 7200)
        await r.setex(key, expires - 60, token)
        return token
    finally:
        await r.close()


@router.post("/login", response_model=TokenResponse)
async def wx_login(req: WxLoginRequest, db: AsyncSession = Depends(get_db)):
    """WeChat code-for-token exchange, then issue JWT.

    Supports dev mode: code starting with 'dev_' bypasses WeChat API.
    """
    # ── Dev mode bypass ──
    if req.code and req.code.startswith("dev_"):
        dev_openid = f"dev_{req.code[4:]}"[:64]
        result = await db.execute(select(User).where(User.openid == dev_openid))
        user = result.scalar_one_or_none()
        if not user:
            user = User(openid=dev_openid, nickname=req.code[4:][:32])
            db.add(user)
            await db.flush()
        await db.commit()
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    # ── Production: WeChat code exchange ──
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.WX_APP_ID,
                "secret": settings.WX_APP_SECRET,
                "js_code": req.code,
                "grant_type": "authorization_code",
            },
        )
        data = resp.json()

    openid = data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail=f"WeChat login failed: {data.get('errmsg', 'unknown')}")

    session_key = data.get("session_key")

    # Find or create user
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, unionid=data.get("unionid"), session_key=session_key)
        db.add(user)
        await db.flush()
    else:
        user.session_key = session_key

    await db.commit()
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload["sub"]
    access_token = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/phone")
async def get_phone(
    req: PhoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get phone number via WeChat server-side API using mini-program access token."""
    # Dev mode: accept mock phone
    if req.code and req.code.startswith("dev_"):
        current_user.phone = "13800138000"
        await db.commit()
        return {"msg": "ok", "phone": current_user.phone}

    token = await _get_wx_access_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={token}",
            json={"code": req.code},
        )
        data = resp.json()

    if data.get("errcode") != 0:
        raise HTTPException(
            status_code=400,
            detail=f"WeChat phone API failed: {data.get('errmsg', 'unknown')}",
        )

    phone_info = data.get("phone_info", {})
    pure_phone = phone_info.get("purePhoneNumber")
    if not pure_phone:
        raise HTTPException(status_code=400, detail="Phone number not available")

    current_user.phone = pure_phone
    await db.commit()
    return {"phone": pure_phone}
