from datetime import date, time
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_user, get_club_admin
from app.models.models import User, Club, ClubMember, Venue, BookingOrder, SettlementRecord
from app.models.models import ClubMemberRole
from app.schemas.schemas import (
    ClubCreate, ClubUpdate, ClubBrief, ClubDetail, PaginatedResponse,
    VenueBrief, ClubListParams, ClubStats,
    CourtSlotRow, CourtSlotCell, VenueSlotGridResponse,
)
from app.models.models import VenueTimeSlot, SlotStatus, VenueStatus

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=PaginatedResponse)
async def list_clubs(
    lat: float = Query(None),
    lng: float = Query(None),
    sport: str = Query(None),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Club).where(Club.status == "active")
    count_query = select(func.count(Club.id)).where(Club.status == "active")

    if keyword:
        query = query.where(Club.name.ilike(f"%{keyword}%"))
        count_query = count_query.where(Club.name.ilike(f"%{keyword}%"))

    if sport:
        query = query.where(Club.sport_types.contains(sport))
        count_query = count_query.where(Club.sport_types.contains(sport))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size).order_by(Club.id.desc()))
    clubs = result.scalars().all()

    return PaginatedResponse(
        items=[ClubBrief.model_validate(c) for c in clubs],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=ClubDetail)
async def create_club(
    req: ClubCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    club = Club(
        name=req.name,
        sport_types=req.sport_types,
        description=req.description,
        cover_image=req.cover_image or (req.images[0] if req.images else None),
        images=req.images,
        documents=req.documents,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        contact_phone=req.contact_phone,
    )
    db.add(club)
    await db.flush()

    # Creator becomes owner
    member = ClubMember(club_id=club.id, user_id=current_user.id, role=ClubMemberRole.owner)
    db.add(member)

    # Upgrade user role if not already
    role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
    if role == "user":
        current_user.role = "club_admin"

    await db.flush()

    return _club_to_detail(club)


@router.get("/{club_id}", response_model=ClubDetail)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Club).where(Club.id == club_id))
    club = result.scalar_one_or_none()
    if not club:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Club not found")

    return await _club_to_detail_async(club, db)


@router.put("/{club_id}", response_model=ClubDetail)
async def update_club(
    club_id: int,
    req: ClubUpdate,
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Club).where(Club.id == club_id))
    club = result.scalar_one_or_none()
    if not club:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Club not found")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(club, key, value)

    return await _club_to_detail_async(club, db)


def _club_to_detail(club: Club) -> ClubDetail:
    """Build ClubDetail from ORM object without triggering lazy load."""
    return ClubDetail(
        id=club.id,
        name=club.name,
        sport_types=club.sport_types,
        cover_image=club.cover_image,
        address=club.address,
        latitude=club.latitude,
        longitude=club.longitude,
        status=club.status.value if hasattr(club.status, 'value') else str(club.status),
        description=club.description,
        images=club.images,
        documents=club.documents,
        contact_phone=club.contact_phone,
        venues=[],
        created_at=club.created_at,
    )


async def _club_to_detail_async(club: Club, db: AsyncSession) -> ClubDetail:
    """Build ClubDetail with venues loaded from query."""
    detail = _club_to_detail(club)
    v_result = await db.execute(
        select(Venue).where(Venue.club_id == club.id)
    )
    venues = v_result.scalars().all()
    detail.venues = [VenueBrief.model_validate(v) for v in venues]
    return detail


@router.get("/{club_id}/venues")
async def club_venues(club_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Venue).where(Venue.club_id == club_id).order_by(Venue.sort_order)
    )
    venues = result.scalars().all()
    return [VenueBrief.model_validate(v) for v in venues]


@router.get("/{club_id}/stats", response_model=ClubStats)
async def club_stats(
    club_id: int,
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    today = date_type.today()

    # Total venues
    v_result = await db.execute(
        select(func.count(Venue.id)).where(Venue.club_id == club_id)
    )
    total_venues = v_result.scalar() or 0

    # Total orders
    o_result = await db.execute(
        select(func.count(BookingOrder.id)).where(BookingOrder.club_id == club_id)
    )
    total_orders = o_result.scalar() or 0

    # Total revenue (paid + completed)
    rev_result = await db.execute(
        select(func.coalesce(func.sum(BookingOrder.amount), 0))
        .where(BookingOrder.club_id == club_id)
        .where(BookingOrder.status.in_(("paid", "completed")))
    )
    total_revenue = rev_result.scalar() or 0

    # Today orders
    today_orders_result = await db.execute(
        select(func.count(BookingOrder.id))
        .where(BookingOrder.club_id == club_id)
        .where(func.date(BookingOrder.created_at) == today)
    )
    today_orders = today_orders_result.scalar() or 0

    # Today revenue
    today_rev_result = await db.execute(
        select(func.coalesce(func.sum(BookingOrder.amount), 0))
        .where(BookingOrder.club_id == club_id)
        .where(func.date(BookingOrder.created_at) == today)
        .where(BookingOrder.status.in_(("paid", "completed")))
    )
    today_revenue = today_rev_result.scalar() or 0

    return ClubStats(
        total_venues=total_venues,
        total_orders=total_orders,
        total_revenue=total_revenue,
        venue_utilization=0.0,  # TODO: calculate real utilization
        today_orders=today_orders,
        today_revenue=today_revenue,
    )


@router.get("/{club_id}/venue-slots")
async def get_club_venue_slots(
    club_id: int,
    query_date: date = Query(..., alias="date"),
    db: AsyncSession = Depends(get_db),
):
    """Return all venues for a club and their time slots for a specific date,
    formatted as a grid (rows = time, columns = venues)."""
    # Get club
    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    # Get active venues for club
    v_result = await db.execute(
        select(Venue)
        .where(Venue.club_id == club_id, Venue.status == VenueStatus.active)
        .order_by(Venue.sort_order)
    )
    venues = v_result.scalars().all()
    if not venues:
        return VenueSlotGridResponse(
            club={"id": club.id, "name": club.name, "address": club.address,
                  "contact_phone": club.contact_phone, "images": club.images or []},
            venues=[],
            rows=[],
        )

    # Build price map from venues to avoid lazy loads
    price_map = {v.id: v.price_per_hour for v in venues}

    # Get all slots for all venues on the date
    venue_ids = [v.id for v in venues]
    slot_result = await db.execute(
        select(VenueTimeSlot)
        .where(
            VenueTimeSlot.venue_id.in_(venue_ids),
            VenueTimeSlot.date == query_date,
        )
        .order_by(VenueTimeSlot.start_time)
    )
    slots = slot_result.scalars().all()

    # Group slots by start_time
    from collections import defaultdict
    time_groups = defaultdict(dict)
    for slot in slots:
        time_key = slot.start_time.strftime("%H:%M")
        price = slot.price_override if slot.price_override is not None else price_map.get(slot.venue_id, 0)
        time_groups[time_key][slot.venue_id] = CourtSlotCell(
            slot_id=slot.id,
            venue_id=slot.venue_id,
            start_time=slot.start_time,
            end_time=slot.end_time,
            price=price,
            status=slot.status.value if hasattr(slot.status, "value") else str(slot.status),
        )

    # Build rows: for each time, list cells in venue order
    rows = []
    for time_key in sorted(time_groups.keys()):
        cells = []
        for venue in venues:
            cell = time_groups[time_key].get(venue.id)
            if cell:
                cells.append(cell)
            else:
                # No slot for this venue at this time - mark as maintenance/unavailable
                cells.append(CourtSlotCell(
                    slot_id=0,
                    venue_id=venue.id,
                    start_time=_time_from_str(time_key),
                    end_time=_time_from_str(time_key),
                    price=0,
                    status="maintenance",
                ))
        rows.append(CourtSlotRow(time_label=time_key, cells=cells))

    return VenueSlotGridResponse(
        club={
            "id": club.id,
            "name": club.name,
            "address": club.address,
            "contact_phone": club.contact_phone,
            "images": club.images or [],
        },
        venues=[
            {"id": v.id, "name": v.name, "sport_type": v.sport_type,
             "price_per_hour": v.price_per_hour}
            for v in venues
        ],
        rows=rows,
    )


def _time_from_str(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)
