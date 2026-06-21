from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import (
    User, ClubMember, Notification, BookingOrder, Venue, VenueTimeSlot,
)
from app.schemas.schemas import (
    UserMeResponse, UserUpdate, PaginatedResponse, NotificationBrief,
    BookingDetail,
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
        role=current_user.role.value if hasattr(current_user.role, 'value') else current_user.role,
        created_at=current_user.created_at,
        managed_club_ids=club_ids,
        ntrp_level=current_user.ntrp_level,
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
    if req.phone is not None:
        current_user.phone = req.phone
    if req.ntrp_level is not None:
        current_user.ntrp_level = req.ntrp_level
    await db.commit()
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


@router.get("/me/bookings", response_model=PaginatedResponse)
async def my_bookings(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's booking orders."""
    query = (
        select(BookingOrder, Venue.name, VenueTimeSlot.date,
               VenueTimeSlot.start_time, VenueTimeSlot.end_time)
        .join(Venue, BookingOrder.venue_id == Venue.id)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.user_id == current_user.id)
    )
    count_query = select(func.count(BookingOrder.id)).where(
        BookingOrder.user_id == current_user.id
    )

    if status:
        query = query.where(BookingOrder.status == status)
        count_query = count_query.where(BookingOrder.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(BookingOrder.created_at.desc())
        .offset(offset).limit(page_size)
    )
    rows = result.all()

    items = []
    for row in rows:
        order, venue_name, slot_date, slot_start, slot_end = row
        items.append(BookingDetail(
            id=order.id, order_no=order.order_no, user_id=order.user_id,
            venue_id=order.venue_id, slot_id=order.slot_id, club_id=order.club_id,
            amount=order.amount, status=order.status.value,
            payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id,
            cancel_reason=order.cancel_reason, cancel_time=order.cancel_time,
            created_at=order.created_at,
            venue_name=venue_name, club_name=None,
            slot_date=slot_date, slot_start=slot_start, slot_end=slot_end,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
