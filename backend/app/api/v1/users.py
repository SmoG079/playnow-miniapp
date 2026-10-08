from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, literal, String, union_all, cast, or_
from app.core.database import get_db
from app.api.deps import get_current_user, _v
from app.models.models import (
    User, ClubMember, Notification, BookingOrder, Venue, Club,
    VenueTimeSlot, OrderStatus, MatchPost, MatchRegistration, Tournament, TournamentRegistration,
)
from app.schemas.schemas import (
    UserMeResponse, UserUpdate, PaginatedResponse, NotificationBrief,
    BookingDetail, PostBrief, MyPostRegistration,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/managed-tournaments", response_model=PaginatedResponse)
async def managed_tournaments(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from app.models.models import TournamentAudit
    from app.api.v1.tournaments import brief
    role = _v(current_user.role)
    managed = select(ClubMember.club_id).where(ClubMember.user_id == current_user.id)
    created = select(TournamentAudit.tournament_id).where(
        TournamentAudit.actor_id == current_user.id, TournamentAudit.action == "created")
    query = select(Tournament, Club.name).join(Club, Club.id == Tournament.club_id)
    if role != "platform_admin":
        scope = Tournament.id.in_(created)
        if role == "club_admin":
            scope = or_(scope, Tournament.club_id.in_(managed))
        query = query.where(scope)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await db.execute(query.order_by(Tournament.created_at.desc(), Tournament.id.desc())
                            .offset((page - 1) * page_size).limit(page_size))).all()
    created_ids = set((await db.execute(created)).scalars().all())
    club_ids = set((await db.execute(managed)).scalars().all()) if role == "club_admin" else set()
    return PaginatedResponse(items=[dict(**brief(t), club_name=name,
        can_manage=t.id in created_ids or role == "platform_admin" or (role == "club_admin" and t.club_id in club_ids))
        for t, name in rows], total=total, page=page, page_size=page_size)


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


@router.get("/me/notifications/{notification_id:int}", response_model=NotificationBrief)
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


@router.put("/me/notifications/{notification_id:int}/read")
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
        .where(BookingOrder.business_type == "booking")
    )

    count_query = select(func.count(BookingOrder.id)).where(
        BookingOrder.user_id == current_user.id,
        BookingOrder.business_type == "booking",
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
        .outerjoin(MatchRegistration, (MatchRegistration.post_id == MatchPost.id)
                   & MatchRegistration.status.in_(("pending", "approved")))
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


@router.get("/me/post-registrations", response_model=PaginatedResponse)
async def my_post_registrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MatchRegistration, MatchPost, Club.name)
        .join(MatchPost, MatchPost.id == MatchRegistration.post_id)
        .outerjoin(Club, Club.id == MatchPost.club_id)
        .where(MatchRegistration.user_id == current_user.id)
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await db.execute(
        query.order_by(MatchRegistration.created_at.desc(), MatchRegistration.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    items = [MyPostRegistration(
        id=reg.id, activity_id=post.id, post_id=post.id, user_id=reg.user_id,
        status=_v(reg.status), message=reg.message, created_at=reg.created_at,
        post_title=post.title, post_status=_v(post.status),
        preferred_date=post.preferred_date, preferred_start=post.preferred_start,
        preferred_end=post.preferred_end, club_id=post.club_id, club_name=club_name,
    ) for reg, post, club_name in rows]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get('/me/tournaments', response_model=PaginatedResponse)
async def my_tournaments(page: int = Query(1,ge=1),page_size: int = Query(20,ge=1,le=50),current_user: User = Depends(get_current_user),db: AsyncSession = Depends(get_db)):
    """Read current published versions; never copy stale brackets into personal records."""
    from app.models.models import Tournament, TournamentRegistration
    from app.api.v1.tournaments import get_tournament, get_draw
    from app.services.tournament_engine import personal_position
    query=select(Tournament).join(TournamentRegistration,TournamentRegistration.tournament_id==Tournament.id).where(TournamentRegistration.user_id==current_user.id)
    total=(await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    events=(await db.execute(query.order_by(Tournament.start_time.desc(),Tournament.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
    items=[]
    for t in events:
        detail=await get_tournament(t.id,current_user,db)
        if detail['draw_version'] != t.published_version:
            if t.published_version:
                detail.update(await get_draw(t.id,t.published_version,current_user,db))
            else:detail.update(teams=[],matches=[])
        provisional = not t.published_version and bool(detail.get('participant_preview'))
        if provisional:detail.update(teams=detail['participant_preview']['teams'],matches=detail['participant_preview']['matches'])
        items.append(dict(id=t.id,activity_id=t.id,title=t.title,start_time=t.start_time,status=_v(t.status),draw_version=t.published_version,
                          provisional=provisional,registration=detail['my_registration'],teams=detail['teams'],registrations=detail['registrations'],
                          my_draw=personal_position(detail['teams'],detail['matches'],current_user.id)))
    return PaginatedResponse(items=items,total=total,page=page,page_size=page_size)


@router.get("/me/activities", response_model=PaginatedResponse)
async def my_activities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A lightweight mixed record page; detail/draw data stays in its own tables."""
    from app.models.models import Tournament, TournamentRegistration
    post_query = select(
        MatchPost.id.label("activity_id"), literal("post").label("kind"),
        MatchRegistration.id.label("registration_id"), MatchPost.title,
        MatchRegistration.status.cast(String(16)).label("status"),
        MatchRegistration.created_at.label("registered_at"), MatchPost.club_id,
    ).join(MatchRegistration, MatchRegistration.post_id == MatchPost.id).where(
        MatchRegistration.user_id == current_user.id)
    tournament_query = select(
        Tournament.id.label("activity_id"), literal("tournament").label("kind"),
        TournamentRegistration.id.label("registration_id"), Tournament.title,
        TournamentRegistration.status.cast(String(16)).label("status"),
        TournamentRegistration.created_at.label("registered_at"), Tournament.club_id,
    ).join(TournamentRegistration, TournamentRegistration.tournament_id == Tournament.id).where(
        TournamentRegistration.user_id == current_user.id)
    records = union_all(post_query, tournament_query).subquery()
    total = await db.scalar(select(func.count()).select_from(records)) or 0
    rows = (await db.execute(select(records).order_by(
        records.c.registered_at.desc(), records.c.activity_id.desc()
    ).offset((page - 1) * page_size).limit(page_size))).mappings().all()
    return PaginatedResponse(items=[dict(row) for row in rows], total=total,
                             page=page, page_size=page_size)


@router.get("/me/registrations", response_model=PaginatedResponse)
async def my_registrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's match and tournament registrations."""
    matches = select(
        MatchRegistration.id.label("id"),
        literal("match_post").label("ref_type"),
        MatchPost.id.label("ref_id"),
        MatchPost.title.label("title"),
        MatchPost.preferred_date.label("preferred_date"),
        MatchPost.preferred_start.label("preferred_start"),
        cast(MatchRegistration.status, String).label("status"),
        MatchRegistration.created_at.label("created_at"),
    ).join(MatchPost, MatchRegistration.post_id == MatchPost.id).where(
        MatchRegistration.user_id == current_user.id
    )
    tournaments = select(
        TournamentRegistration.id.label("id"),
        literal("tournament").label("ref_type"),
        Tournament.id.label("ref_id"),
        Tournament.title.label("title"),
        func.date(Tournament.start_time).label("preferred_date"),
        func.time(Tournament.start_time).label("preferred_start"),
        cast(TournamentRegistration.status, String).label("status"),
        TournamentRegistration.created_at.label("created_at"),
    ).join(Tournament, TournamentRegistration.tournament_id == Tournament.id).where(
        TournamentRegistration.user_id == current_user.id
    )
    registrations = union_all(matches, tournaments).subquery()
    total = (await db.execute(select(func.count()).select_from(registrations))).scalar() or 0
    result = await db.execute(
        select(registrations).order_by(
            registrations.c.created_at.desc(), registrations.c.ref_type, registrations.c.id.desc()
        ).offset((page - 1) * page_size).limit(page_size)
    )
    return PaginatedResponse(
        items=[dict(row) for row in result.mappings().all()],
        total=total, page=page, page_size=page_size,
    )
