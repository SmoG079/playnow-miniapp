from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.config import get_settings
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.api.deps import get_current_user, get_club_admin
from app.models.models import (
    User, Club, Tournament, TournamentRegistration, TournamentStatus,
    TournamentRegStatus, Venue, VenueTimeSlot, SlotStatus,
    Notification, NotificationType, BookingOrder, OrderStatus,
)
from app.schemas.schemas import (
    TournamentCreate, TournamentUpdate, TournamentBrief, TournamentDetail,
    TournamentRegBrief, TournamentListParams, PaginatedResponse, BookingDetail,
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])
settings = get_settings()


def _generate_order_no() -> str:
    from datetime import datetime
    import uuid
    return datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()


@router.get("", response_model=PaginatedResponse)
async def list_tournaments(
    club_id: int = Query(None),
    sport: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Tournament, Club.name)
        .join(Club, Tournament.club_id == Club.id)
    )
    count_query = select(func.count(Tournament.id))

    if club_id:
        query = query.where(Tournament.club_id == club_id)
        count_query = count_query.where(Tournament.club_id == club_id)
    if sport:
        query = query.where(Tournament.sport_type == sport)
        count_query = count_query.where(Tournament.sport_type == sport)
    if status:
        query = query.where(Tournament.status == status)
        count_query = count_query.where(Tournament.status == status)

    query = query.order_by(Tournament.start_time)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for t, club_name in rows:
        items.append(TournamentBrief(
            id=t.id, club_id=t.club_id, title=t.title,
            sport_type=t.sport_type, start_time=t.start_time, end_time=t.end_time,
            venue_id=t.venue_id, entry_fee=t.entry_fee,
            max_participants=t.max_participants,
            current_participants=t.current_participants or 0,
            cover_image=t.cover_image, status=t.status.value,
            created_at=t.created_at, club_name=club_name,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=TournamentBrief)
async def create_tournament(
    req: TournamentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify club admin
    _ = await get_club_admin(req.club_id, current_user, db)

    tournament = Tournament(
        club_id=req.club_id,
        title=req.title,
        description=req.description,
        sport_type=req.sport_type,
        start_time=req.start_time,
        end_time=req.end_time,
        venue_id=req.venue_id,
        lock_venue=req.lock_venue,
        max_participants=req.max_participants,
        entry_fee=req.entry_fee,
        cover_image=req.cover_image,
        prize=req.prize,
        status=TournamentStatus.draft,
    )
    db.add(tournament)
    await db.flush()
    await db.refresh(tournament)

    # Lock venue slots if requested
    if req.lock_venue and req.venue_id:
        await _lock_tournament_slots(db, req.venue_id, req.start_time, req.end_time)

    result = await db.execute(select(Club).where(Club.id == req.club_id))
    club = result.scalar_one()

    return TournamentBrief(
        id=tournament.id, club_id=tournament.club_id, title=tournament.title,
        sport_type=tournament.sport_type, start_time=tournament.start_time,
        end_time=tournament.end_time, venue_id=tournament.venue_id,
        entry_fee=tournament.entry_fee or 0,
        max_participants=tournament.max_participants,
        current_participants=0,
        cover_image=tournament.cover_image, status=tournament.status.value,
        created_at=tournament.created_at, club_name=club.name,
    )


@router.get("/{tournament_id}", response_model=TournamentDetail)
async def get_tournament(tournament_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tournament, Club.name)
        .join(Club, Tournament.club_id == Club.id)
        .where(Tournament.id == tournament_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Tournament not found")
    t, club_name = row

    reg_result = await db.execute(
        select(TournamentRegistration, User.nickname, User.avatar_url)
        .join(User, TournamentRegistration.user_id == User.id)
        .where(TournamentRegistration.tournament_id == tournament_id)
    )
    reg_rows = reg_result.all()
    regs = [
        TournamentRegBrief(id=r.id, user_id=r.user_id, status=r.status.value,
                           user_nickname=nick, user_avatar=av)
        for r, nick, av in reg_rows
    ]

    return TournamentDetail(
        id=t.id, club_id=t.club_id, title=t.title,
        sport_type=t.sport_type, start_time=t.start_time, end_time=t.end_time,
        venue_id=t.venue_id, entry_fee=t.entry_fee or 0,
        max_participants=t.max_participants,
        current_participants=t.current_participants or 0,
        cover_image=t.cover_image, status=t.status.value,
        created_at=t.created_at, club_name=club_name,
        description=t.description, prize=t.prize, lock_venue=t.lock_venue,
        registrations=regs,
    )


@router.put("/{tournament_id}", response_model=TournamentBrief)
async def update_tournament(
    tournament_id: int,
    req: TournamentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tournament).where(Tournament.id == tournament_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    _ = await get_club_admin(t.club_id, current_user, db)

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(t, key, value)

    await db.flush()
    await db.refresh(t)

    result = await db.execute(select(Club).where(Club.id == t.club_id))
    club = result.scalar_one()

    return TournamentBrief(
        id=t.id, club_id=t.club_id, title=t.title,
        sport_type=t.sport_type, start_time=t.start_time, end_time=t.end_time,
        venue_id=t.venue_id, entry_fee=t.entry_fee or 0,
        max_participants=t.max_participants,
        current_participants=t.current_participants or 0,
        cover_image=t.cover_image, status=t.status.value,
        created_at=t.created_at, club_name=club.name,
    )


@router.post("/{tournament_id}/register")
async def register_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tournament).where(Tournament.id == tournament_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if t.status != TournamentStatus.open:
        raise HTTPException(status_code=400, detail="Tournament is not open for registration")
    if t.max_participants and (t.current_participants or 0) >= t.max_participants:
        raise HTTPException(status_code=400, detail="Tournament is full")

    existing = await db.execute(
        select(TournamentRegistration).where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already registered")

    reg = TournamentRegistration(
        tournament_id=tournament_id,
        user_id=current_user.id,
    )
    db.add(reg)

    order = None
    if t.entry_fee and t.entry_fee > 0:
        # Create pending booking order for entry fee
        order = BookingOrder(
            order_no=_generate_order_no(),
            user_id=current_user.id,
            venue_id=t.venue_id,
            slot_id=None,
            club_id=t.club_id,
            amount=t.entry_fee,
            status=OrderStatus.pending,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)
        reg.order_id = order.id
        reg.status = TournamentRegStatus.registered
    else:
        # Free tournament: confirm immediately
        reg.status = TournamentRegStatus.confirmed
        t.current_participants = (t.current_participants or 0) + 1

    await db.flush()
    await db.refresh(reg)

    return {
        "msg": "ok",
        "registration_id": reg.id,
        "order": BookingDetail(
            id=order.id,
            order_no=order.order_no,
            user_id=order.user_id,
            venue_id=order.venue_id,
            slot_id=order.slot_id,
            club_id=order.club_id,
            amount=order.amount,
            status=order.status.value,
            payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id,
            cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time,
            created_at=order.created_at,
        ) if order else None,
    }


@router.post("/{tournament_id}/pay")
async def pay_tournament(
    tournament_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TournamentRegistration, Tournament)
        .join(Tournament, TournamentRegistration.tournament_id == Tournament.id)
        .where(
            TournamentRegistration.tournament_id == tournament_id,
            TournamentRegistration.user_id == current_user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found")
    reg, tournament = row

    if reg.status == TournamentRegStatus.confirmed:
        raise HTTPException(status_code=400, detail="Already paid")
    if not reg.order_id:
        raise HTTPException(status_code=400, detail="No pending order")

    order_result = await db.execute(
        select(BookingOrder).where(
            BookingOrder.id == reg.order_id,
            BookingOrder.user_id == current_user.id,
            BookingOrder.status == OrderStatus.pending,
        )
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pending order not found")

    if not current_user.openid:
        raise HTTPException(status_code=400, detail="User openid not available")

    wxpay = get_wxpay()
    try:
        result = wxpay.pay(
            description=tournament.title,
            out_trade_no=order.order_no,
            amount={"total": int(order.amount * 100)},
            payer={"openid": current_user.openid},
        )
        prepay_id = result.get("prepay_id")
        if not prepay_id:
            raise HTTPException(status_code=500, detail="WeChat pay did not return prepay_id")
        return build_jsapi_params(wxpay, prepay_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WeChat pay order creation failed: {str(e)}")


async def _lock_tournament_slots(db: AsyncSession, venue_id: int, start_time, end_time):
    """Lock all venue slots within the tournament time range."""
    from datetime import datetime as dt
    result = await db.execute(
        select(VenueTimeSlot).where(
            VenueTimeSlot.venue_id == venue_id,
            VenueTimeSlot.date >= start_time.date(),
            VenueTimeSlot.date <= end_time.date(),
            VenueTimeSlot.status == SlotStatus.available,
        )
    )
    slots = result.scalars().all()
    for slot in slots:
        slot_start = dt.combine(slot.date, slot.start_time)
        slot_end = dt.combine(slot.date, slot.end_time)
        if slot_start < end_time and slot_end > start_time:
            slot.status = SlotStatus.maintenance
