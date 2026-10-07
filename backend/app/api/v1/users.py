from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from app.core.database import get_db
from app.api.deps import get_current_user, _v
from app.models.models import (
    User, ClubMember, Notification, BookingOrder, Venue, Club,
    VenueTimeSlot, OrderStatus, MatchPost, MatchRegistration,
)
from app.schemas.schemas import (
    UserMeResponse, UserUpdate, PaginatedResponse, NotificationBrief,
    BookingDetail, PostBrief,
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


@router.get("/me/notifications/{notification_id}", response_model=NotificationBrief)
async def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationBrief.model_validate(notif)


@router.put("/me/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    return {"msg": "ok"}


@router.put("/me/notifications/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    return {"msg": "ok"}


@router.get("/me/notifications/unread-count")
async def unread_notification_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": result.scalar() or 0}


@router.get("/me/bookings", response_model=PaginatedResponse)
async def my_bookings(
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(
            BookingOrder,
            Venue.name.label("venue_name"),
            Club.name.label("club_name"),
        )
        .join(Venue, BookingOrder.venue_id == Venue.id)
        .join(Club, BookingOrder.club_id == Club.id)
        .where(BookingOrder.user_id == current_user.id)
    )

    count_query = select(func.count(BookingOrder.id)).where(
        BookingOrder.user_id == current_user.id
    )

    if status:
        try:
            order_status = OrderStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
        query = query.where(BookingOrder.status == order_status)
        count_query = count_query.where(BookingOrder.status == order_status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(BookingOrder.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = result.all()

    items = []
    for row in rows:
        order = row[0]
        # Load full consecutive slot range for display
        slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
        slots_result = await db.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
        )
        slots = sorted(slots_result.scalars().all(), key=lambda s: s.start_time)
        first_slot = slots[0] if slots else None
        last_slot = slots[-1] if slots else None
        items.append(
            BookingDetail(
                id=order.id,
                order_no=order.order_no,
                user_id=order.user_id,
                venue_id=order.venue_id,
                slot_id=order.slot_id,
                slot_ids=order.slot_ids,
                club_id=order.club_id,
                amount=order.amount,
                status=_v(order.status),
                payment_time=order.payment_time,
                wx_transaction_id=order.wx_transaction_id,
                cancel_reason=order.cancel_reason,
                cancel_time=order.cancel_time,
                created_at=order.created_at,
                venue_name=row.venue_name,
                club_name=row.club_name,
                slot_date=first_slot.date if first_slot else None,
                slot_start=first_slot.start_time if first_slot else None,
                slot_end=last_slot.end_time if last_slot else None,
            )
        )

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/me/posts", response_model=PaginatedResponse)
async def my_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MatchPost, User.nickname, User.avatar_url, Club.name,
               func.count(MatchRegistration.id))
        .join(User, MatchPost.user_id == User.id)
        .outerjoin(Club, MatchPost.club_id == Club.id)
        .outerjoin(MatchRegistration, MatchRegistration.post_id == MatchPost.id)
        .where(MatchPost.user_id == current_user.id)
        .group_by(MatchPost.id)
        .order_by(MatchPost.created_at.desc())
    )
    count_q = select(func.count(MatchPost.id)).where(MatchPost.user_id == current_user.id)
    total_r = await db.execute(count_q)
    total = total_r.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.all()
    items = []
    for row in rows:
        post, nickname, avatar, club_name, reg_count = row
        items.append(PostBrief(
            id=post.id, club_id=post.club_id, user_id=post.user_id,
            title=post.title, sport_type=post.sport_type,
            preferred_date=post.preferred_date,
            preferred_start=post.preferred_start,
            preferred_end=post.preferred_end,
            players_needed=post.players_needed,
            level_required=post.level_required,
            status=post.status.value,
            created_at=post.created_at,
            user_nickname=nickname, user_avatar=avatar,
            club_name=club_name, registration_count=reg_count or 0,
            venue_id=post.venue_id, booking_id=post.booking_id,
            price=post.price, notes=post.notes,
            images=post.images, approval_required=post.approval_required,
        ))
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
