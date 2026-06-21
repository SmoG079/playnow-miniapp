import json
import uuid
import httpx
import time
import logging
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis import acquire_lock, release_lock, redis_client
from app.core.rate_limit import check_rate_limit
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.api.deps import get_current_user, get_club_admin, get_platform_admin, _v
from app.models.models import (
    User, UserRole, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    SettlementRecord, SettlementStatus, Notification, NotificationType, Club, ClubMember,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, RefundStatus, PaymentLog,
)
from app.schemas.schemas import (
    BookingCreateRequest, BookingDetail, BookingListParams,
    CancelRequest, RefundRequest, PaginatedResponse, SettlementDetail,
)
from app.services.settlement import (
    generate_settlement_out_order_no, execute_settlement, query_settlement_status,
    _to_cents,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])
settings = get_settings()

# Timezone convention: DB timestamps and internal comparisons use UTC-naive datetimes;
# business calculations convert explicitly from local timezone when needed.


def _utc_now() -> datetime:
    """Return current time as UTC-naive datetime, consistent with DB timestamps."""
    return datetime.utcnow()


REFUND_RETRYABLE_CODES = {"SYSTEM_ERROR", "BIZERR_NEED_RETRY"}


def _is_refund_retryable(exc: Exception) -> bool:
    msg = str(exc).upper()
    if any(code in msg for code in REFUND_RETRYABLE_CODES):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    return False


def _refund_backoff_seconds(attempt: int) -> int:
    base = settings.REFUND_RETRY_BACKOFF_BASE_SECONDS
    return min(base * (2 ** attempt), 1800)


def _generate_order_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()


@router.post("", response_model=BookingDetail)
async def create_booking(
    req: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock one or more consecutive slots and create a pending booking order."""
    settings = get_settings()
    await check_rate_limit(
        f"rate:booking:{current_user.id}",
        max_requests=settings.RATE_LIMIT_BOOKING_PER_MINUTE,
        window_seconds=60,
    )

    try:
        slot_ids = req.resolved_slot_ids()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not slot_ids:
        raise HTTPException(status_code=422, detail="slot_id or slot_ids is required")

    if len(slot_ids) > 1 and len(set(slot_ids)) != len(slot_ids):
        raise HTTPException(status_code=422, detail="Duplicate slot IDs")

    # Acquire DB row locks ordered by slot id to prevent deadlock
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids)).with_for_update()
    )
    slots = result.scalars().all()
    if len(slots) != len(slot_ids):
        raise HTTPException(status_code=404, detail="One or more slots not found")

    # Sort by start_time to validate consecutiveness and compute range
    slots = sorted(slots, key=lambda s: s.start_time)
    first_slot = slots[0]
    venue_id = first_slot.venue_id
    slot_date = first_slot.date

    tz = ZoneInfo("Asia/Shanghai")
    now_local = datetime.now(tz).replace(microsecond=0)

    # Validate all slots belong to same venue/date, are consecutive, available and not past
    for i, slot in enumerate(slots):
        if slot.venue_id != venue_id or slot.date != slot_date:
            raise HTTPException(status_code=422, detail="All slots must belong to the same venue and date")
        if i > 0 and slot.start_time != slots[i - 1].end_time:
            raise HTTPException(status_code=422, detail="Slots must be consecutive")
        slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz, microsecond=0)
        if now_local >= slot_datetime:
            raise HTTPException(status_code=400, detail="Slot time has already passed")
        if _v(slot.status) != "available":
            raise HTTPException(status_code=409, detail="One or more slots are not available")

    # Get venue + club
    venue_result = await db.execute(select(Venue).where(Venue.id == venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue or _v(venue.status) != "active":
        raise HTTPException(status_code=400, detail="Venue not available")

    club_result = await db.execute(select(Club).where(Club.id == venue.club_id))
    club = club_result.scalar_one_or_none()

    # Acquire Redis locks for all slots
    acquired_lock_keys = []
    lock_owner = str(current_user.id)
    try:
        for slot in slots:
            lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
            acquired = await acquire_lock(lock_key, lock_owner, settings.BOOKING_LOCK_TTL_SECONDS)
            if not acquired:
                # Release any locks we already acquired
                for released_key in acquired_lock_keys:
                    await release_lock(released_key, lock_owner)
                raise HTTPException(status_code=409, detail="One or more slots are being booked by another user")
            acquired_lock_keys.append(lock_key)

        # Mark all slots locked
        total_price = Decimal("0")
        for slot in slots:
            slot.status = SlotStatus.locked
            slot.locked_by = current_user.id
            slot.locked_at = _utc_now()
            duration_minutes = (slot.end_time.hour * 60 + slot.end_time.minute) - (slot.start_time.hour * 60 + slot.start_time.minute)
            base_price = slot.price_override if slot.price_override is not None else venue.price_per_hour
            total_price += base_price * Decimal(duration_minutes) / Decimal("60")

        # Create order
        order = BookingOrder(
            order_no=_generate_order_no(),
            user_id=current_user.id,
            venue_id=venue.id,
            slot_id=first_slot.id,
            slot_ids=slot_ids,
            club_id=venue.club_id,
            amount=total_price,
            status=OrderStatus.pending,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)
        await db.commit()
    except HTTPException:
        for released_key in acquired_lock_keys:
            await release_lock(released_key, lock_owner)
        raise
    except Exception:
        for released_key in acquired_lock_keys:
            await release_lock(released_key, lock_owner)
        raise

    return BookingDetail(
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
        prepay_id=order.prepay_id,
        prepay_id_created_at=order.prepay_id_created_at,
        cancel_reason=order.cancel_reason,
        cancel_time=order.cancel_time,
        created_at=order.created_at,
        venue_name=venue.name,
        club_name=club.name if club else None,
        slot_date=first_slot.date,
        slot_start=first_slot.start_time,
        slot_end=slots[-1].end_time,
        slot_datetime=datetime.combine(first_slot.date, first_slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
        refund_amount=order.refund_amount,
        refund_id=order.refund_id,
        refund_time=order.refund_time,
        refund_status=order.refund_status,
    )


@router.get("/config")
async def get_booking_config():
    """Return public booking configuration (e.g. free cancellation window)."""
    return {"free_cancel_hours": settings.FREE_CANCEL_HOURS}


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BookingOrder, Venue, Club)
        .join(Venue, BookingOrder.venue_id == Venue.id)
        .join(Club, BookingOrder.club_id == Club.id)
        .where(BookingOrder.id == booking_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, venue, club = row

    # Load all slots for the booking to compute the full time range
    slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
    slots_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
    )
    slots = sorted(slots_result.scalars().all(), key=lambda s: s.start_time)
    first_slot = slots[0] if slots else None
    last_slot = slots[-1] if slots else None

    # Check ownership or admin
    if order.user_id != current_user.id:
        role = _v(current_user.role)
        if role == "platform_admin":
            pass  # allowed
        elif role == "club_admin":
            # Verify admin manages this club
            member = await db.execute(
                select(ClubMember).where(
                    ClubMember.club_id == order.club_id,
                    ClubMember.user_id == current_user.id,
                )
            )
            if not member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    return BookingDetail(
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
        prepay_id=order.prepay_id,
        prepay_id_created_at=order.prepay_id_created_at,
        cancel_reason=order.cancel_reason,
        cancel_time=order.cancel_time,
        created_at=order.created_at,
        venue_name=venue.name,
        club_name=club.name,
        slot_date=first_slot.date if first_slot else None,
        slot_start=first_slot.start_time if first_slot else None,
        slot_end=last_slot.end_time if last_slot else None,
        slot_datetime=datetime.combine(first_slot.date, first_slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat() if first_slot else None,
        refund_amount=order.refund_amount,
        refund_id=order.refund_id,
        refund_time=order.refund_time,
        refund_status=order.refund_status,
    )


@router.post("/{booking_id}/pay")
async def pay_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Placeholder: mark order as paid directly (WeChat Pay V3 pending)."""
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if _v(order.status) == "paid":
        return {"msg": "ok", "order_no": order.order_no, "amount": str(order.amount), "already_paid": True}
    if _v(order.status) != "pending":
        raise HTTPException(status_code=400, detail="Order is not pending")

    # Mark order as paid
    order.status = OrderStatus.paid
    order.payment_time = _utc_now()
    order.wx_transaction_id = f"dev_{order.order_no}"

    # Release locks, mark slots as booked
    slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
    slots_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
    )
    for slot in slots_result.scalars().all():
        slot.status = SlotStatus.booked
        slot.locked_by = None
        slot.locked_at = None
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key)

    # Create settlement record
    import logging
    _log = logging.getLogger(__name__)
    _log.info("Payment placeholder: order %s marked as paid (dev mode)", order.order_no)

    return {"msg": "ok", "order_no": order.order_no, "amount": str(order.amount)}


@router.post("/wx-notify")
async def wx_pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """WeChat payment callback. Verifies and acknowledges immediately, then queues heavy processing to Celery."""
    body = await request.body()

    # P0-4: Verify/decrypt callback BEFORE parsing body or recording nonce
    try:
        wxpay = get_wxpay()
        headers_dict = dict(request.headers)
        decrypted = wxpay.decrypt_callback(headers_dict, body)
        data = json.loads(decrypted)
    except Exception as e:
        logger.error("Callback verify/decrypt failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid callback")

    # P0-6: Timestamp and nonce replay protection (after successful verification)
    timestamp = request.headers.get("Wechatpay-Timestamp")
    nonce = request.headers.get("Wechatpay-Nonce")
    now = int(time.time())
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid callback timestamp")
    if not timestamp or abs(now - ts) > 300:
        logger.warning("Callback timestamp invalid: timestamp=%s now=%s", timestamp, now)
        raise HTTPException(status_code=400, detail="Callback timestamp invalid")

    if not nonce:
        logger.warning("Callback missing nonce")
        raise HTTPException(status_code=400, detail="Callback nonce missing")

    redis = redis_client
    nonce_key = f"wx:callback:nonce:{nonce}"
    # SET NX EX atomically; if key exists, SET returns None
    set_result = await redis.set(nonce_key, "1", nx=True, ex=3600)
    if set_result is None:
        logger.warning("Duplicate WeChat callback nonce: %s", nonce)
        return {"code": "SUCCESS"}

    event_type = data.get("event_type", "")
    out_trade_no = data.get("out_trade_no")

    # Log all callbacks
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    log = PaymentLog(
        order_id=order.id if order else None,
        type="callback",
        event_type=event_type,
        raw_data={"headers": dict(request.headers), "decrypted": data},
    )
    db.add(log)
    await db.commit()

    # P0-5: Acknowledge SUCCESS immediately, queue heavy work to Celery
    from app.tasks.tasks import process_wx_callback
    process_wx_callback.delay(event_type, data)

    return {"code": "SUCCESS"}


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int,
    req: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BookingOrder).where(BookingOrder.id == booking_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
    slots_result = await db.execute(select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids)))
    slots = slots_result.scalars().all()

    if _v(order.status) not in ("pending", "paid"):
        raise HTTPException(status_code=400, detail="Cannot cancel in current status")

    order.status = OrderStatus.cancelled
    order.cancel_reason = req.reason
    order.cancel_time = _utc_now()

    # Release all slots
    for slot in slots:
        slot.status = SlotStatus.available
        slot.locked_by = None
        slot.locked_at = None
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key)

    return {"msg": "ok"}


@router.post("/{booking_id}/refund")
async def refund_booking(
    booking_id: int,
    req: RefundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refund a paid booking order via WeChat Pay V3 (club/platform admin only)."""
    await check_rate_limit(
        f"rate:refund:{current_user.id}",
        max_requests=settings.RATE_LIMIT_REFUND_PER_MINUTE,
        window_seconds=60,
    )
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Authorization: club admin for this club or platform admin only
    role = _v(current_user.role)
    if role == "platform_admin":
        pass
    elif role == "club_admin":
        member = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == order.club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    if _v(order.status) != "paid":
        raise HTTPException(status_code=400, detail="Only paid orders can be refunded")

    if not order.wx_transaction_id:
        raise HTTPException(status_code=400, detail="Missing WeChat transaction id")

    # Calculate refund amount (admin can specify, default to full)
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(status_code=400, detail="Refund amount must be greater than 0")
    refund_amount = req.amount if req.amount is not None else order.amount
    if refund_amount > order.amount:
        raise HTTPException(status_code=400, detail="Refund amount cannot exceed order amount")

    wxpay = get_wxpay()
    out_refund_no = _generate_order_no()

    # Create refund record BEFORE calling WeChat (pre-creation for idempotency)
    refund_record = RefundRecord(
        order_id=order.id,
        out_refund_no=out_refund_no,
        amount=refund_amount,
        reason=req.reason or "管理员退款",
        status=RefundStatus.pending,
    )
    db.add(refund_record)
    await db.flush()

    try:
        wxpay.refund(
            out_refund_no=out_refund_no,
            transaction_id=order.wx_transaction_id,
            amount={
                "refund": _to_cents(refund_amount),
                "total": _to_cents(order.amount),
                "currency": "CNY",
            },
            reason=req.reason or "管理员退款",
        )
    except Exception as e:
        if _is_refund_retryable(e):
            # Retryable failure: schedule retry
            refund_record.status = RefundStatus.failed
            refund_record.scheduled_at = _utc_now() + timedelta(seconds=_refund_backoff_seconds(0))
            refund_record.fail_reason = str(e)[:512]
            order.refund_status = RefundStatus.failed
            await db.commit()
            from app.tasks.tasks import retry_failed_refunds
            retry_failed_refunds.delay()
            return {
                "msg": "Refund queued for retry",
                "status": "refunding",
                "out_refund_no": out_refund_no,
            }
        # Non-retryable failure
        refund_record.fail_reason = str(e)[:512]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"WeChat refund failed: {str(e)}")

    order.status = OrderStatus.refunding
    order.refund_amount = refund_amount
    order.refund_id = out_refund_no
    order.refund_status = RefundStatus.pending
    order.cancel_reason = req.reason or "管理员退款"
    order.cancel_time = _utc_now()

    # Slot stays booked until REFUND.SUCCESS callback arrives
    await db.commit()

    return {"msg": "ok", "out_refund_no": out_refund_no, "refund_amount": str(refund_amount), "status": "refunding"}


@router.get("/{booking_id}/refund-records")
async def list_refund_records(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List refund records for a booking order."""
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Authorization: booking owner, club admin for the club, or platform admin
    if order.user_id != current_user.id:
        role = _v(current_user.role)
        if role == "platform_admin":
            pass
        elif role == "club_admin":
            member = await db.execute(
                select(ClubMember).where(
                    ClubMember.club_id == order.club_id,
                    ClubMember.user_id == current_user.id,
                )
            )
            if not member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(
        select(RefundRecord)
        .where(RefundRecord.order_id == order.id)
        .order_by(RefundRecord.created_at.desc())
    )
    records = result.scalars().all()

    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "out_refund_no": r.out_refund_no,
            "wx_refund_id": r.wx_refund_id,
            "amount": str(r.amount),
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in records
    ]


@router.get("/club/{club_id}", response_model=PaginatedResponse)
async def club_orders(
    club_id: int,
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(BookingOrder, Venue.name) \
        .join(Venue, BookingOrder.venue_id == Venue.id) \
        .where(BookingOrder.club_id == club_id)

    count_query = select(func.count(BookingOrder.id)).where(BookingOrder.club_id == club_id)

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
    result = await db.execute(query.order_by(BookingOrder.created_at.desc()).offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        order, venue_name = row
        # Load all slots for this booking to show the full consecutive range
        slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
        slots_result = await db.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
        )
        slots = sorted(slots_result.scalars().all(), key=lambda s: s.start_time)
        first_slot = slots[0] if slots else None
        last_slot = slots[-1] if slots else None
        slot_date = first_slot.date if first_slot else None
        slot_start = first_slot.start_time if first_slot else None
        slot_end = last_slot.end_time if last_slot else None
        slot_datetime = datetime.combine(slot_date, slot_start).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat() if first_slot else None
        items.append(BookingDetail(
            id=order.id, order_no=order.order_no, user_id=order.user_id,
            venue_id=order.venue_id, slot_id=order.slot_id, slot_ids=order.slot_ids,
            club_id=order.club_id,
            amount=order.amount, status=_v(order.status), payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, prepay_id=order.prepay_id,
            prepay_id_created_at=order.prepay_id_created_at, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end, slot_datetime=slot_datetime,
            refund_amount=order.refund_amount, refund_id=order.refund_id,
            refund_time=order.refund_time, refund_status=order.refund_status,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/settlements", response_model=PaginatedResponse)
async def list_settlements(
    status: str = Query(None),
    club_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SettlementRecord, BookingOrder.order_no)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .order_by(SettlementRecord.created_at.desc())
    )
    count_stmt = (
        select(func.count(SettlementRecord.id))
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
    )

    if status:
        stmt = stmt.where(SettlementRecord.status == status)
        count_stmt = count_stmt.where(SettlementRecord.status == status)
    if club_id:
        stmt = stmt.where(BookingOrder.club_id == club_id)
        count_stmt = count_stmt.where(BookingOrder.club_id == club_id)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for rec, order_no in rows:
        items.append(SettlementDetail(
            id=rec.id,
            order_id=rec.order_id,
            order_no=order_no,
            total_amount=rec.total_amount,
            platform_amount=rec.platform_amount,
            club_amount=rec.club_amount,
            split_ratio=rec.split_ratio,
            status=_v(rec.status),
            wx_split_order_no=rec.wx_split_order_no,
            out_order_no=rec.out_order_no,
            retry_count=rec.retry_count,
            scheduled_at=rec.scheduled_at,
            completed_at=rec.completed_at,
            fail_reason=rec.fail_reason,
            created_at=rec.created_at,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/settlements/{settlement_id}/query", response_model=SettlementDetail)
async def query_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await query_settlement_status(db, settlement_id)
    await db.commit()

    # Fetch order_no for the response
    order_result = await db.execute(
        select(BookingOrder.order_no).where(BookingOrder.id == rec.order_id)
    )
    order_no = order_result.scalar() or ""

    return SettlementDetail(
        id=rec.id,
        order_id=rec.order_id,
        order_no=order_no,
        total_amount=rec.total_amount,
        platform_amount=rec.platform_amount,
        club_amount=rec.club_amount,
        split_ratio=rec.split_ratio,
        status=_v(rec.status),
        wx_split_order_no=rec.wx_split_order_no,
        out_order_no=rec.out_order_no,
        retry_count=rec.retry_count,
        scheduled_at=rec.scheduled_at,
        completed_at=rec.completed_at,
        fail_reason=rec.fail_reason,
        created_at=rec.created_at,
    )


@router.post("/settlements/{settlement_id}/retry", response_model=SettlementDetail)
async def retry_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await db.get(SettlementRecord, settlement_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if _v(rec.status) == "completed":
        raise HTTPException(status_code=400, detail="Settlement already completed")
    rec.status = SettlementStatus.pending
    rec.retry_count = 0
    await db.commit()
    rec = await execute_settlement(db, settlement_id)
    await db.commit()  # persist processing state / wx_split_order_no
    if _v(rec.status) == "processing":
        try:
            rec = await query_settlement_status(db, settlement_id)
            await db.commit()
        except Exception:
            logger.exception("Settlement %s query status failed during retry, but processing state is committed", settlement_id)
    await db.commit()

    # Fetch order_no for the response
    order_result = await db.execute(
        select(BookingOrder.order_no).where(BookingOrder.id == rec.order_id)
    )
    order_no = order_result.scalar() or ""

    return SettlementDetail(
        id=rec.id,
        order_id=rec.order_id,
        order_no=order_no,
        total_amount=rec.total_amount,
        platform_amount=rec.platform_amount,
        club_amount=rec.club_amount,
        split_ratio=rec.split_ratio,
        status=_v(rec.status),
        wx_split_order_no=rec.wx_split_order_no,
        out_order_no=rec.out_order_no,
        retry_count=rec.retry_count,
        scheduled_at=rec.scheduled_at,
        completed_at=rec.completed_at,
        fail_reason=rec.fail_reason,
        created_at=rec.created_at,
    )
