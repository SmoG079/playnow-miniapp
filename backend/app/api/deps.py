from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_token
from app.models.models import User, ClubMember


def _v(field) -> str:
    """Safely get string value from enum or string field (asyncmy returns strings)."""
    return field.value if hasattr(field, 'value') else str(field)


async def get_current_user(
    authorization: str = Header(..., description="Bearer {token}"),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth header")
    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_club_admin(
    club_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    role = _v(current_user.role)
    if role == "platform_admin":
        return current_user
    if role == "club_admin":
        result = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if result.scalar_one_or_none():
            return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires club admin permission")


async def get_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if _v(current_user.role) != "platform_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires platform admin")
    return current_user
