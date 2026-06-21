from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
import httpx
import logging
from app.core.database import get_db
from app.core.config import get_settings
from app.api.deps import get_current_user, get_club_admin, _v
from app.models.models import User, Club, ClubMember, Venue, BookingOrder, SettlementRecord
from app.models.models import ClubMemberRole
from app.utils.geo import haversine
from app.schemas.schemas import (
    ClubCreate, ClubUpdate, ClubBrief, ClubDetail, PaginatedResponse,
    VenueBrief, ClubListParams, ClubStats,
    CourtSlotRow, CourtSlotCell, VenueSlotGridResponse,
)
from app.models.models import VenueTimeSlot, SlotStatus, VenueStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clubs", tags=["clubs"])


class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=256)


class GeocodeResponse(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: str


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(
    req: GeocodeRequest,
    _: User = Depends(get_current_user),
):
    """Proxy Tencent Map geocoder so the key stays on the backend."""
    settings = get_settings()
    if not settings.TENCENT_MAP_KEY:
        return GeocodeResponse(address=req.address)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://apis.map.qq.com/ws/geocoder/v1/",
                params={
                    "address": req.address,
                    "key": settings.TENCENT_MAP_KEY,
                },
            )
            data = resp.json()
    except Exception as exc:
        logger.warning("Tencent geocoder request failed: %s", exc)
        return GeocodeResponse(address=req.address)

    location = data.get("result", {}).get("location") if data.get("status") == 0 else None
    if not location:
        return GeocodeResponse(address=req.address)

    return GeocodeResponse(
        latitude=location.get("lat"),
        longitude=location.get("lng"),
        address=req.address,
    )


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

    has_location = lat is not None and lng is not None
    items = []
    for c in clubs:
        distance = None
        if has_location and c.latitude is not None and c.longitude is not None:
            distance = haversine(
                lat, lng,
                float(c.latitude), float(c.longitude),
            )
        items.append(ClubBrief.model_validate(c).model_copy(update={"distance": distance}))

    if has_location:
        items.sort(key=lambda x: x.distance if x.distance is not None else float("inf"))

    # Increment exposure count for listed clubs
    if clubs:
        await db.execute(
            update(Club)
            .where(Club.id.in_([c.id for c in clubs]))
            .values(exposure_count=Club.exposure_count + 1)
        )
        await db.flush()

    return PaginatedResponse(
        items=items,
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
    role = _v(current_user.role)
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

    club.view_count += 1
    await db.flush()

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
        rules=club.rules,
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

    # Load club for view/exposure counts
    club_result = await db.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

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
        view_count=club.view_count,
        exposure_count=club.exposure_count,
    )


@router.get("/{club_id}/venue-slots")
async def get_club_venue_slots(
    club_id: int,
    query_date: date = Query(..., alias="date"),
    venue_id: Optional[int] = Query(None),
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
    v_query = (
        select(Venue)
        .where(Venue.club_id == club_id, Venue.status == VenueStatus.active)
    )
    if venue_id:
        v_query = v_query.where(Venue.id == venue_id)
    v_query = v_query.order_by(Venue.sort_order)
    v_result = await db.execute(v_query)
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

    # Filter out slots whose start time has already passed (Asia/Shanghai)
    tz = ZoneInfo("Asia/Shanghai")
    now_local = datetime.now(tz).replace(microsecond=0)
    filtered_slots = []
    for slot in slots:
        slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz, microsecond=0)
        if slot_datetime > now_local:
            filtered_slots.append(slot)
    slots = filtered_slots

    # Group slots by start_time
    from collections import defaultdict
    time_groups = defaultdict(dict)
    for slot in slots:
        time_key = slot.start_time.strftime("%H:%M")
        duration_minutes = (slot.end_time.hour * 60 + slot.end_time.minute) - (slot.start_time.hour * 60 + slot.start_time.minute)
        base_price = slot.price_override if slot.price_override is not None else price_map.get(slot.venue_id, 0)
        price = base_price * Decimal(duration_minutes) / Decimal("60")
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
