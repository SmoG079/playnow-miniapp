import logging
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.api.deps import get_current_user, get_club_admin, _v
from app.models.models import User, Venue, VenueTimeSlot, SlotStatus, Club, VenueStatus
from app.schemas.schemas import (
    VenueCreate, VenueUpdate, VenueBrief, VenueDetail,
    SlotGenerateRequest, SlotBrief, SlotDateGroup,
    SlotStatusUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("/{venue_id}", response_model=VenueDetail)
async def get_venue(venue_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Venue).where(Venue.id == venue_id))
    venue = result.scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return VenueDetail.model_validate(venue)


@router.post("/with-club/{club_id}", response_model=VenueBrief)
async def create_venue_for_club(
    club_id: int,
    req: VenueCreate,
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    venue = Venue(
        club_id=club_id,
        name=req.name,
        sport_type=req.sport_type,
        price_per_hour=req.price_per_hour,
        max_capacity=req.max_capacity,
        cover_image=req.cover_image,
        sort_order=req.sort_order,
    )
    db.add(venue)
    await db.flush()
    await db.refresh(venue)
    return VenueBrief.model_validate(venue)


@router.put("/{venue_id}/with-club/{club_id}", response_model=VenueBrief)
async def update_venue(
    venue_id: int,
    club_id: int,
    req: VenueUpdate,
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.club_id == club_id)
    )
    venue = result.scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(venue, key, value)
    await db.flush()
    await db.refresh(venue)
    return VenueBrief.model_validate(venue)


@router.delete("/{venue_id}/with-club/{club_id}")
async def delete_venue(
    venue_id: int,
    club_id: int,
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.club_id == club_id)
    )
    venue = result.scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    venue.status = VenueStatus.closed
    return {"msg": "ok"}


@router.get("/{venue_id}/slots")
async def get_slots(
    venue_id: int,
    date: date = Query(None),
    date_from: date = Query(None),
    date_to: date = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if date:
        date_from = date_to = date
    if not date_from or not date_to:
        raise HTTPException(status_code=422, detail="Provide either 'date' or both 'date_from' and 'date_to'")

    result = await db.execute(
        select(VenueTimeSlot)
        .options(selectinload(VenueTimeSlot.venue))
        .where(
            VenueTimeSlot.venue_id == venue_id,
            VenueTimeSlot.date >= date_from,
            VenueTimeSlot.date <= date_to,
        )
        .order_by(VenueTimeSlot.date, VenueTimeSlot.start_time)
    )
    slots = result.scalars().all()

    grouped = {}
    for slot in slots:
        d = slot.date.isoformat()
        if d not in grouped:
            grouped[d] = []
        grouped[d].append(slot)

    return [
        SlotDateGroup(
            date=date.fromisoformat(k),
            slots=[_slot_to_brief(s) for s in v],
        )
        for k, v in grouped.items()
    ]


def _slot_to_brief(slot: VenueTimeSlot) -> SlotBrief:
    return SlotBrief(
        id=slot.id,
        venue_id=slot.venue_id,
        date=slot.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        price=slot.price_override if slot.price_override is not None else Decimal("0"),
        status=_v(slot.status),
    )


def _effective_price_for_slot(start_time: time, price_rules: list, venue_price: Decimal) -> Decimal:
    """Return the first matching price rule price, else venue default."""
    for rule in price_rules:
        if rule.start_time <= start_time < rule.end_time:
            return rule.price
    return venue_price


async def _require_club_admin_for_venue(
    venue_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Load venue and verify current user is admin of the venue's club."""
    result = await db.execute(select(Venue).where(Venue.id == venue_id))
    venue = result.scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    role = _v(current_user.role)
    if role == "platform_admin":
        return current_user
    if role == "club_admin":
        from app.models.models import ClubMember
        member_result = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == venue.club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if member_result.scalar_one_or_none():
            return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires club admin permission")


@router.post("/{venue_id}/slots/batch")
async def generate_slots(
    venue_id: int,
    req: SlotGenerateRequest,
    _: User = Depends(_require_club_admin_for_venue),
    db: AsyncSession = Depends(get_db),
):
    """Generate time slots for a date range."""
    logger.info(
        "generate_slots called: venue_id=%s date_from=%s date_to=%s start_time=%s end_time=%s interval=%s price_rules=%s",
        venue_id, req.date_from, req.date_to, req.start_time, req.end_time, req.interval_minutes, req.price_rules,
    )
    venue_result = await db.execute(select(Venue).where(Venue.id == venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue:
        logger.warning("generate_slots: venue %s not found", venue_id)
        raise HTTPException(status_code=404, detail="Venue not found")

    current_date = req.date_from
    created = 0
    skipped = 0
    while current_date <= req.date_to:
        slot_start = datetime.combine(current_date, req.start_time)
        slot_end = datetime.combine(current_date, req.end_time)
        logger.debug(
            "generate_slots: processing date=%s slot_start=%s slot_end=%s",
            current_date, slot_start, slot_end,
        )
        while slot_start + timedelta(minutes=req.interval_minutes) <= slot_end:
            next_time = slot_start + timedelta(minutes=req.interval_minutes)
            existing = await db.execute(
                select(VenueTimeSlot).where(
                    VenueTimeSlot.venue_id == venue_id,
                    VenueTimeSlot.date == current_date,
                    VenueTimeSlot.start_time == slot_start.time(),
                )
            )
            if not existing.scalar_one_or_none():
                price = _effective_price_for_slot(
                    slot_start.time(), req.price_rules, venue.price_per_hour
                )
                slot = VenueTimeSlot(
                    venue_id=venue_id,
                    date=current_date,
                    start_time=slot_start.time(),
                    end_time=next_time.time(),
                    price_override=price if price != venue.price_per_hour else None,
                )
                db.add(slot)
                created += 1
            else:
                skipped += 1
            slot_start = next_time
        current_date += timedelta(days=1)

    await db.commit()
    logger.info("generate_slots completed: venue_id=%s created=%s skipped=%s", venue_id, created, skipped)
    return {"created": created, "skipped": skipped, "msg": f"Generated {created} slots"}


@router.patch("/{venue_id}/slots/{slot_id}/status")
async def update_slot_status(
    venue_id: int,
    slot_id: int,
    req: SlotStatusUpdateRequest,
    _: User = Depends(_require_club_admin_for_venue),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a single slot between available and maintenance."""
    result = await db.execute(
        select(VenueTimeSlot).where(
            VenueTimeSlot.id == slot_id,
            VenueTimeSlot.venue_id == venue_id,
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    current_status = _v(slot.status)
    if current_status in ("locked", "booked"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change status of a {current_status} slot",
        )

    new_status = SlotStatus(req.status)
    slot.status = new_status
    await db.flush()

    return {"msg": "ok", "slot_id": slot.id, "status": req.status}
