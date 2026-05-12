from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_user, get_club_admin
from app.models.models import (
    User, Club, Tournament, TournamentRegistration, TournamentStatus,
    TournamentRegStatus, Venue, VenueTimeSlot, SlotStatus,
    Notification, NotificationType,
)
from app.schemas.schemas import (
    TournamentCreate, TournamentUpdate, TournamentBrief, TournamentDetail,
    TournamentRegBrief, TournamentListParams, PaginatedResponse,
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


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
        description=t.description, lock_venue=t.lock_venue,
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
        status=TournamentRegStatus.registered,
    )
    db.add(reg)
    t.current_participants = (t.current_participants or 0) + 1

    # If entry fee > 0, create a booking order for payment
    if t.entry_fee and t.entry_fee > 0:
        # TODO: Create payment flow similar to venue booking
        pass

    return {"msg": "ok"}


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
