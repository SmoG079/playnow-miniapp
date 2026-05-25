from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.api.deps import get_current_user, get_club_admin
from app.models.models import User, Club, ClubMember, Venue, BookingOrder, SettlementRecord
from app.models.models import ClubMemberRole
from app.schemas.schemas import (
    ClubCreate, ClubUpdate, ClubBrief, ClubDetail, PaginatedResponse,
    VenueBrief, ClubListParams, ClubStats,
)

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
        cover_image=req.cover_image,
        images=req.images,
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
