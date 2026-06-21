import uuid
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis import acquire_lock, release_lock
from app.api.deps import get_current_user, get_club_admin
from app.models.models import (
    User, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    SettlementRecord, Notification, NotificationType, Club,
)
from app.schemas.schemas import (
    BookingCreateRequest, BookingDetail, BookingListParams,
    CancelRequest, PaginatedResponse,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])
settings = get_settings()


def _generate_order_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()


@router.post("", response_model=BookingDetail)
async def create_booking(
    req: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock one or two consecutive slots and create a pending booking order."""
    # Get primary slot
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == req.slot_id)
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.status != SlotStatus.available:
        raise HTTPException(status_code=409, detail="Slot is not available")

    # Get second slot if provided
    slot2 = None
    if req.slot2_id:
        result2 = await db.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id == req.slot2_id)
        )
        slot2 = result2.scalar_one_or_none()
        if not slot2:
            raise HTTPException(status_code=404, detail="Second slot not found")
        if slot2.status != SlotStatus.available:
            raise HTTPException(status_code=409, detail="Second slot is not available")
        if slot2.venue_id != slot.venue_id:
            raise HTTPException(status_code=400, detail="Slots must belong to same venue")

    # Get venue + club
    venue_result = await db.execute(select(Venue).where(Venue.id == slot.venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue or venue.status.value != "active":
        raise HTTPException(status_code=400, detail="Venue not available")

    club_result = await db.execute(select(Club).where(Club.id == venue.club_id))
    club = club_result.scalar_one_or_none()

    # Try Redis lock on primary slot
    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
    acquired = await acquire_lock(lock_key, str(current_user.id), settings.BOOKING_LOCK_TTL_SECONDS)
    if not acquired:
        raise HTTPException(status_code=409, detail="Slot is being booked by another user")

    # Lock second slot too
    lock2_key = None
    if slot2:
        lock2_key = f"slot:{slot2.venue_id}:{slot2.date}:{slot2.start_time}"
        acquired2 = await acquire_lock(lock2_key, str(current_user.id), settings.BOOKING_LOCK_TTL_SECONDS)
        if not acquired2:
            await release_lock(lock_key)
            raise HTTPException(status_code=409, detail="Second slot is being booked")

    try:
        # Mark slot(s) locked
        slot.status = SlotStatus.locked
        slot.locked_by = current_user.id
        slot.locked_at = datetime.utcnow()

        if slot2:
            slot2.status = SlotStatus.locked
            slot2.locked_by = current_user.id
            slot2.locked_at = datetime.utcnow()

        # Calculate price: sum of both slots
        p1 = slot.price_override if slot.price_override else venue.price_per_hour
        price = p1
        if slot2:
            p2 = slot2.price_override if slot2.price_override else venue.price_per_hour
            price = p1 + p2

        # Use latest end_time for display
        effective_end = slot2.end_time if slot2 else slot.end_time

        # Create order
        order = BookingOrder(
            order_no=_generate_order_no(),
            user_id=current_user.id,
            venue_id=venue.id,
            slot_id=slot.id,
            club_id=venue.club_id,
            amount=price,
            status=OrderStatus.pending,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)

        return BookingDetail(
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
            venue_name=venue.name,
            club_name=club.name if club else None,
            slot_date=slot.date,
            slot_start=slot.start_time,
            slot_end=effective_end,
        )
    except Exception:
        await release_lock(lock_key)
        if lock2_key:
            await release_lock(lock2_key)
        raise


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BookingOrder, Venue, Club, VenueTimeSlot)
        .join(Venue, BookingOrder.venue_id == Venue.id)
        .join(Club, BookingOrder.club_id == Club.id)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == booking_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, venue, club, slot = row

    # Check ownership or admin
    if order.user_id != current_user.id:
        # Allow club admin to view
        if current_user.role.value not in ("club_admin", "platform_admin"):
            raise HTTPException(status_code=403, detail="Not authorized")

    return BookingDetail(
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
        venue_name=venue.name,
        club_name=club.name,
        slot_date=slot.date,
        slot_start=slot.start_time,
        slot_end=slot.end_time,
    )


@router.post("/{booking_id}/pay")
async def pay_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate WeChat JSAPI payment for a pending booking."""
    result = await db.execute(select(BookingOrder).where(BookingOrder.id == booking_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="Order is not in pending status")

    # TODO: WeChat Pay V3 JSAPI integration placeholder
    # Currently marks order as paid directly for dev/testing
    order.status = OrderStatus.paid
    order.payment_time = datetime.utcnow()
    order.wx_transaction_id = f"dev_{order.order_no}"

    # Mark slot(s) as booked
    slot_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
    )
    slot = slot_result.scalar_one_or_none()
    if slot:
        slot.status = SlotStatus.booked
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key)

    # Release sibling locked slot
    sibling_result = await db.execute(
        select(VenueTimeSlot).where(
            VenueTimeSlot.venue_id == slot.venue_id,
            VenueTimeSlot.date == slot.date,
            VenueTimeSlot.locked_by == current_user.id,
            VenueTimeSlot.status == SlotStatus.locked,
        )
    )
    for sib in sibling_result.scalars().all():
        sib.status = SlotStatus.booked
        sib.locked_by = None
        sib.locked_at = None
        sib_key = f"slot:{sib.venue_id}:{sib.date}:{sib.start_time}"
        await release_lock(sib_key)

    # Create settlement record
    club_result = await db.execute(select(Club).where(Club.id == order.club_id))
    club = club_result.scalar_one_or_none()
    split_ratio = club.split_ratio if club else Decimal("0.100")
    platform_amount = order.amount * split_ratio
    club_amount = order.amount - platform_amount
    settlement = SettlementRecord(
        order_id=order.id,
        total_amount=order.amount,
        platform_amount=platform_amount,
        club_amount=club_amount,
        split_ratio=split_ratio,
        status="pending",
    )
    db.add(settlement)

    # Create notification
    notif = Notification(
        user_id=order.user_id,
        type=NotificationType.booking,
        title="预约成功",
        content=f"您的场地预约已支付成功，订单号 {order.order_no}",
        ref_id=order.id,
        ref_type="booking",
    )
    db.add(notif)

    return {"msg": "ok", "order_no": order.order_no, "amount": str(order.amount)}


@router.post("/wx-notify")
async def wx_pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """WeChat payment callback. Verify signature and update order status."""
    body = await request.body()
    headers = request.headers
    # TODO: Implement WeChat Pay V3 signature verification
    # For now, parse the callback body
    import json
    data = json.loads(body)

    out_trade_no = data.get("out_trade_no")
    transaction_id = data.get("transaction_id")

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    if not order:
        return {"code": "FAIL", "message": "Order not found"}

    # Idempotency check
    if order.status == OrderStatus.paid:
        return {"code": "SUCCESS"}

    order.status = OrderStatus.paid
    order.payment_time = datetime.utcnow()
    order.wx_transaction_id = transaction_id

    # Mark primary slot as booked
    slot_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
    )
    slot = slot_result.scalar_one_or_none()
    if slot:
        slot.status = SlotStatus.booked
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key)

    # Also release any other locked slot by same user on same venue/date
    sibling_result = await db.execute(
        select(VenueTimeSlot).where(
            VenueTimeSlot.venue_id == slot.venue_id,
            VenueTimeSlot.date == slot.date,
            VenueTimeSlot.locked_by == order.user_id,
            VenueTimeSlot.status == SlotStatus.locked,
        )
    )
    for sib in sibling_result.scalars().all():
        sib.status = SlotStatus.booked
        sib.locked_by = None
        sib.locked_at = None
        sib_key = f"slot:{sib.venue_id}:{sib.date}:{sib.start_time}"
        await release_lock(sib_key)

    # Create settlement record
    club_result = await db.execute(select(Club).where(Club.id == order.club_id))
    club = club_result.scalar_one_or_none()
    split_ratio = club.split_ratio if club else Decimal("0.100")
    platform_amount = order.amount * split_ratio
    club_amount = order.amount - platform_amount

    settlement = SettlementRecord(
        order_id=order.id,
        total_amount=order.amount,
        platform_amount=platform_amount,
        club_amount=club_amount,
        split_ratio=split_ratio,
        status="pending",
    )
    db.add(settlement)

    # Create notification
    notif = Notification(
        user_id=order.user_id,
        type=NotificationType.booking,
        title="预约成功",
        content=f"您的场地预约已支付成功，订单号 {order.order_no}",
        ref_id=order.id,
        ref_type="booking",
    )
    db.add(notif)

    return {"code": "SUCCESS"}


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int,
    req: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BookingOrder, VenueTimeSlot)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == booking_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, slot = row

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    if order.status not in (OrderStatus.pending, OrderStatus.paid):
        raise HTTPException(status_code=400, detail="Cannot cancel in current status")

    # Calculate refund
    now = datetime.utcnow()
    slot_datetime = datetime.combine(slot.date, slot.start_time)
    hours_before = (slot_datetime - now).total_seconds() / 3600

    if hours_before >= settings.FREE_CANCEL_HOURS:
        refund_amount = order.amount
    elif hours_before >= 0:
        refund_amount = order.amount * Decimal("0.5")
    else:
        raise HTTPException(status_code=400, detail="Cannot cancel after start time")

    order.status = OrderStatus.refunding if refund_amount > 0 else OrderStatus.cancelled
    order.cancel_reason = req.reason
    order.cancel_time = now
    order.refund_amount = refund_amount

    # Release primary slot
    slot.status = SlotStatus.available
    slot.locked_by = None
    slot.locked_at = None
    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
    await release_lock(lock_key)

    # Also release any sibling locked slot
    sibling_result = await db.execute(
        select(VenueTimeSlot).where(
            VenueTimeSlot.venue_id == slot.venue_id,
            VenueTimeSlot.date == slot.date,
            VenueTimeSlot.locked_by == order.user_id,
            VenueTimeSlot.status == SlotStatus.locked,
        )
    )
    for sib in sibling_result.scalars().all():
        sib.status = SlotStatus.available
        sib.locked_by = None
        sib.locked_at = None
        sib_key = f"slot:{sib.venue_id}:{sib.date}:{sib.start_time}"
        await release_lock(sib_key)

    # TODO: Trigger WeChat refund API if paid

    return {"msg": "ok", "refund_amount": str(refund_amount)}


@router.get("/club/{club_id}", response_model=PaginatedResponse)
async def club_orders(
    club_id: int,
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(BookingOrder, Venue.name, VenueTimeSlot.date, VenueTimeSlot.start_time, VenueTimeSlot.end_time) \
        .join(Venue, BookingOrder.venue_id == Venue.id) \
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id) \
        .where(BookingOrder.club_id == club_id)

    count_query = select(func.count(BookingOrder.id)).where(BookingOrder.club_id == club_id)

    if status:
        query = query.where(BookingOrder.status == status)
        count_query = count_query.where(BookingOrder.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(BookingOrder.created_at.desc()).offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        order, venue_name, slot_date, slot_start, slot_end = row
        items.append(BookingDetail(
            id=order.id, order_no=order.order_no, user_id=order.user_id,
            venue_id=order.venue_id, slot_id=order.slot_id, club_id=order.club_id,
            amount=order.amount, status=order.status.value, payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
