from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, ClubMember, Notification
from app.schemas.schemas import (
    UserMeResponse, UserUpdate, PaginatedResponse, NotificationBrief,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ClubMember.club_id).where(ClubMember.user_id == current_user.id)
    )
    club_ids = [row[0] for row in result.fetchall()]
    return UserMeResponse(
        id=current_user.id,
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        phone=current_user.phone,
        role=current_user.role.value,
        created_at=current_user.created_at,
        managed_club_ids=club_ids,
    )


@router.put("/me")
async def update_me(
    req: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.nickname is not None:
        current_user.nickname = req.nickname
    if req.avatar_url is not None:
        current_user.avatar_url = req.avatar_url
    return {"msg": "ok"}


@router.get("/me/notifications", response_model=PaginatedResponse)
async def my_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(offset).limit(page_size)
    )
    items = result.scalars().all()
    count_result = await db.execute(
        select(Notification).where(Notification.user_id == current_user.id)
    )
    total = len(count_result.scalars().all())
    return PaginatedResponse(
        items=[NotificationBrief.model_validate(n) for n in items],
        total=total, page=page, page_size=page_size,
    )
