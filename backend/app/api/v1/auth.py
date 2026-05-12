import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.models import User
from app.schemas.schemas import WxLoginRequest, TokenResponse, RefreshRequest, PhoneRequest

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
async def wx_login(req: WxLoginRequest, db: AsyncSession = Depends(get_db)):
    """WeChat code-for-token exchange, then issue JWT."""
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

    # Find or create user
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        user = User(openid=openid, unionid=data.get("unionid"))
        db.add(user)
        await db.flush()

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
async def get_phone(req: PhoneRequest, db: AsyncSession = Depends(get_db)):
    """Decrypt WeChat phone number. The actual decrypt happens on the mini program side.
    This endpoint receives the decrypted phone and saves it."""
    # Phone decryption is done client-side with session_key.
    # Here we accept the already-decrypted phone number.
    # In production, pass session_key to decrypt server-side or accept from client's getPhoneNumber result.
    raise HTTPException(status_code=501, detail="Use client-side phone decryption with getPhoneNumber")
