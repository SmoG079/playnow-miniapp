from datetime import date, time, datetime, timedelta, timezone
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
from app.services.tencent_map import GEOCODER_URL, geocoder_params
from app.services.discovery import distance_expr, city_name
from app.services.pricing import slot_charge
from app.services.slots import ensure_slots, validate_booking_date
from app.core.config import get_settings
from app.api.deps import get_current_user, get_optional_user, get_club_admin, _v
from app.models.models import User, Club, ClubMember, Venue, BookingOrder, SettlementRecord, Notification, NotificationType
from app.models.models import ClubMemberRole
from app.utils.geo import haversine
from app.schemas.schemas import (
    ClubCreate, ClubUpdate, ClubBrief, ClubDetail, PaginatedResponse,
    VenueBrief, ClubListParams, ClubStats,
    CourtSlotRow, CourtSlotCell, VenueSlotGridResponse,
)
from app.models.models import VenueTimeSlot, SlotStatus, VenueStatus


def _parse_time(val):
    """Convert 'HH:MM' string to time, or return default."""
    if not val:
        return None
    try:
        return time.fromisoformat(val)
    except (ValueError, TypeError):
        return None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clubs", tags=["clubs"])


class GeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=256)


class GeocodeResponse(BaseModel):
    city: Optional[str] = None
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
                GEOCODER_URL,
                params=geocoder_params({"address": req.address}, settings.TENCENT_MAP_KEY, getattr(settings, "TENCENT_MAP_SK", "")),
                headers={"x-legacy-url-decode": "no"},
            )
            data = resp.json()
    except Exception:
        # Exception URLs may contain the key and signature.
        logger.warning("Tencent geocoder request failed")
        return GeocodeResponse(address=req.address)

    location = data.get("result", {}).get("location") if data.get("status") == 0 else None
    if not location:
        return GeocodeResponse(address=req.address)

    return GeocodeResponse(
        city=data.get("result", {}).get("address_components", {}).get("city"),
        latitude=location.get("lat"),
        longitude=location.get("lng"),
        address=req.address,
    )


@router.get("", response_model=PaginatedResponse)
async def list_clubs(
    city: Optional[str] = None,
    lat: float = Query(None),
    lng: float = Query(None),
    sport: str = Query(None),
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = select(Club).where(Club.status == "active", Club.approval_status == "approved")
    count_query = select(func.count(Club.id)).where(Club.status == "active", Club.approval_status == "approved")

    if city is not None:
        selected_city = city_name(city)
        in_city = select(Venue.id).where(Venue.club_id == Club.id, Venue.status == VenueStatus.active, Venue.city == selected_city).correlate(Club).exists() if selected_city else False
        query = query.where(in_city)
        count_query = count_query.where(in_city)

    if keyword:
        query = query.where(Club.name.ilike(f"%{keyword}%"))
        count_query = count_query.where(Club.name.ilike(f"%{keyword}%"))

    if sport:
        query = query.where(Club.sport_types.contains(sport))
        count_query = count_query.where(Club.sport_types.contains(sport))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    has_location = lat is not None and lng is not None
    venue_distance = distance_expr(lat, lng, Venue.latitude, Venue.longitude) if has_location else None
    nearest = select(Venue.id).where(Venue.club_id == Club.id, Venue.status == VenueStatus.active)
    if city is not None:
        nearest = nearest.where(Venue.city == city_name(city))
    if has_location:
        nearest = nearest.order_by(venue_distance.is_(None), venue_distance, Venue.id)
    else:
        nearest = nearest.order_by(Venue.sort_order, Venue.id)
    nearest = nearest.correlate(Club).limit(1).scalar_subquery()
    query = query.add_columns(Venue).outerjoin(Venue, Venue.id == nearest)
    if has_location:
        query = query.order_by(venue_distance.is_(None), venue_distance, Club.id.desc())
    else:
        query = query.order_by(Club.id.desc())
    result = await db.execute(query.offset((page-1)*page_size).limit(page_size))
    items, clubs = [], []
    for c, v in result.all():
        clubs.append(c)
        distance = haversine(lat, lng, float(v.latitude), float(v.longitude)) if has_location and v and v.latitude is not None and v.longitude is not None else None
        items.append(ClubBrief.model_validate(c).model_copy(update={
            "distance": distance, "nearest_venue_id": v.id if v else None,
            "nearest_venue_name": v.name if v else None,
            "venue_address": v.address if v else None,
            "venue_city": v.city if v else None,
            "venue_latitude": float(v.latitude) if v and v.latitude is not None else None,
            "venue_longitude": float(v.longitude) if v and v.longitude is not None else None,
        }))

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


@router.get("/managed", response_model=PaginatedResponse)
async def managed_clubs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = _v(current_user.role)
    if role not in ("club_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Requires club admin permission")
    query = select(Club)
    if role != "platform_admin":
        query = query.where(Club.id.in_(
            select(ClubMember.club_id).where(ClubMember.user_id == current_user.id)
        ))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    clubs = (await db.execute(query.order_by(Club.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return PaginatedResponse(items=[ClubBrief.model_validate(c) for c in clubs],
                             total=total, page=page, page_size=page_size)


@router.post("", response_model=ClubDetail)
async def create_club(
    req: ClubCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.privacy import validate_certification_documents
    await validate_certification_documents(db, req.documents, current_user)
    opening = _parse_time(req.opening_time)
    closing = _parse_time(req.closing_time)
    if opening is None or closing is None or closing <= opening:
        raise HTTPException(status_code=422, detail="营业结束时间需晚于开始时间")
    club = Club(
        approval_status="pending", status="inactive", created_by=current_user.id,
        city=req.city,
        name=req.name,
        sport_types=req.sport_types,
        description=req.description,
        rules=req.rules,
        cover_image=req.cover_image or (req.images[0] if req.images else None),
        images=req.images,
        documents=req.documents,
        address=req.address,
        latitude=req.latitude,
        longitude=req.longitude,
        contact_phone=req.contact_phone,
        opening_time=opening,
        closing_time=closing,
    )
    db.add(club)
    await db.flush()

    admins = (await db.execute(select(User.id).where(User.role == "platform_admin"))).scalars().all()
    for admin_id in admins:
        db.add(Notification(user_id=admin_id, type=NotificationType.system,
            title="新的俱乐部创建申请", content=f"《{club.name}》等待审核，请在申请处理页面查看。",
            ref_type="club_application", ref_id=club.id))
    await db.flush()
    # Ownership and the club administrator role are granted only after approval.
    return _club_to_detail(club)


@router.get("/{club_id}", response_model=ClubDetail)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    result = await db.execute(select(Club).where(Club.id == club_id))
    club = result.scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    if club.approval_status != "approved" and (not user or (user.id != club.created_by and _v(user.role) != "platform_admin")):
        raise HTTPException(status_code=404, detail="Club not found")
    club.view_count += 1
    await db.flush()

    detail = await _club_to_detail_async(club, db)
    from app.services.privacy import can_view_club_documents
    if not await can_view_club_documents(db, club, user): detail.documents = None
    return detail


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
        raise HTTPException(status_code=404, detail="Club not found")

    if "documents" in req.model_fields_set:
        from app.services.privacy import validate_certification_documents
        await validate_certification_documents(db, req.documents, _, previous=club.documents)
    update_data = req.model_dump(exclude_unset=True)
    for key in ("opening_time", "closing_time"):
        if key in update_data:
            parsed = _parse_time(update_data[key])
            if parsed is None:
                raise HTTPException(status_code=422, detail="请填写有效的营业时间")
            update_data[key] = parsed
    opening = update_data.get("opening_time", club.opening_time)
    closing = update_data.get("closing_time", club.closing_time)
    if closing <= opening:
        raise HTTPException(status_code=422, detail="营业结束时间需晚于开始时间")
    for key, value in update_data.items():
        setattr(club, key, value)

    return await _club_to_detail_async(club, db)


def _club_to_detail(club: Club) -> ClubDetail:
    """Build ClubDetail from ORM object without triggering lazy load."""
    return ClubDetail(
        id=club.id,
        city=club.city,
        name=club.name,
        sport_types=club.sport_types,
        cover_image=club.cover_image,
        address=club.address,
        latitude=club.latitude,
        longitude=club.longitude,
        approval_status=club.approval_status, review_reason=club.review_reason, reviewed_at=club.reviewed_at,
        status=club.status.value if hasattr(club.status, 'value') else str(club.status),
        description=club.description,
        rules=club.rules,
        images=club.images,
        documents=club.documents,
        contact_phone=club.contact_phone,
        opening_time=club.opening_time,
        closing_time=club.closing_time,
        view_count=club.view_count,
        exposure_count=club.exposure_count,
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
    club = await db.get(Club, club_id)
    if not club or club.approval_status != "approved":
        raise HTTPException(404, "Club not found")
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
    local_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = day_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = start_utc + timedelta(days=1)

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
        .where(BookingOrder.created_at >= start_utc, BookingOrder.created_at < end_utc)
    )
    today_orders = today_orders_result.scalar() or 0

    # Today revenue
    today_rev_result = await db.execute(
        select(func.coalesce(func.sum(BookingOrder.amount), 0))
        .where(BookingOrder.club_id == club_id)
        .where(BookingOrder.created_at >= start_utc, BookingOrder.created_at < end_utc)
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
    validate_booking_date(query_date)
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
    v_query = v_query.order_by(Venue.id).with_for_update()
    v_result = await db.execute(v_query)
    venues = sorted(v_result.scalars().all(), key=lambda v: (v.sort_order or 0, v.id))
    if not venues:
        return VenueSlotGridResponse(
            club={"id": club.id, "name": club.name, "address": club.address,
                  "contact_phone": club.contact_phone, "images": club.images or []},
            venues=[],
            rows=[],
        )

    from app.services.booking_locks import expire_slot_orders
    await expire_slot_orders(db, venue_ids=[v.id for v in venues], day=query_date)
    for venue in sorted(venues, key=lambda v: v.id):
        await ensure_slots(db, venue.id, query_date)

    # Get all slots for all venues on the date
    venue_ids = [v.id for v in venues]
    slot_result = await db.execute(
        select(VenueTimeSlot)
        .where(
            VenueTimeSlot.venue_id.in_(venue_ids),
            VenueTimeSlot.date == query_date,
        )
        .order_by(VenueTimeSlot.id).with_for_update()
    )
    slots = slot_result.scalars().all()

    # Filter out slots whose start time has already passed + release expired locks
    tz = ZoneInfo("Asia/Shanghai")
    now_local = datetime.now(tz).replace(microsecond=0)
    filtered_slots = []
    for slot in slots:
        slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz, microsecond=0)
        if slot_datetime <= now_local:
            continue
        filtered_slots.append(slot)
    slots = filtered_slots

    # Group slots by start_time
    from collections import defaultdict

    time_groups = defaultdict(dict)
    for slot in slots:
        time_key = slot.start_time.strftime("%H:%M")
        venue = next((v for v in venues if v.id == slot.venue_id), None)
        price = slot_charge(venue, slot)
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
             "price_per_hour": v.price_per_hour, "city": v.city, "address": v.address,
             "latitude": v.latitude, "longitude": v.longitude}
            for v in venues
        ],
        rows=rows,
    )


def _time_from_str(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)
