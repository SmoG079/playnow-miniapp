import json
import uuid
import httpx
import time
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis import acquire_lock, release_lock, redis_client
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.api.deps import get_current_user, get_club_admin, get_platform_admin, _v
from app.models.models import (
    User, UserRole, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    SettlementRecord, SettlementStatus, Notification, NotificationType, Club, ClubMember,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, PaymentLog,
)
from app.schemas.schemas import (
    BookingCreateRequest, BookingDetail, BookingListParams, PayResponse,
    CancelRequest, RefundRequest, PaginatedResponse, SettlementDetail,
)
from app.services.settlement import (
    generate_settlement_out_order_no, execute_settlement, query_settlement_status,
    _to_cents,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])
settings = get_settings()


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
    """Lock a slot and create a pending booking order."""
    # Acquire DB row lock first to prevent TOCTOU race condition
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == req.slot_id).with_for_update()
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    # P1-2: reject slots whose start time has already passed (before row lock / expensive work)
    tz = ZoneInfo("Asia/Shanghai")
    slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz, microsecond=0)
    if datetime.now(tz).replace(microsecond=0) >= slot_datetime:
        raise HTTPException(status_code=400, detail="Slot time has already passed")

    if _v(slot.status) != "available":
        raise HTTPException(status_code=409, detail="Slot is not available")

    # Get venue + club
    venue_result = await db.execute(select(Venue).where(Venue.id == slot.venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue or _v(venue.status) != "active":
        raise HTTPException(status_code=400, detail="Venue not available")

    club_result = await db.execute(select(Club).where(Club.id == venue.club_id))
    club = club_result.scalar_one_or_none()

    # Acquire Redis lock inside the DB transaction
    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
    acquired = await acquire_lock(lock_key, str(current_user.id), settings.BOOKING_LOCK_TTL_SECONDS)
    if not acquired:
        raise HTTPException(status_code=409, detail="Slot is being booked by another user")

    try:
        # Mark slot locked
        slot.status = SlotStatus.locked
        slot.locked_by = current_user.id
        slot.locked_at = datetime.utcnow()

        # Calculate price
        price = slot.price_override if slot.price_override is not None else venue.price_per_hour

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
            slot_date=slot.date,
            slot_start=slot.start_time,
            slot_end=slot.end_time,
            refund_amount=order.refund_amount,
            refund_id=order.refund_id,
            refund_time=order.refund_time,
            refund_status=order.refund_status,
        )
    except Exception:
        await release_lock(lock_key, str(current_user.id))
        raise


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
        if _v(current_user.role) not in ("club_admin", "platform_admin"):
            raise HTTPException(status_code=403, detail="Not authorized")

    return BookingDetail(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        venue_id=order.venue_id,
        slot_id=order.slot_id,
        club_id=order.club_id,
        amount=order.amount,
        status=_v(order.status),
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
        refund_amount=order.refund_amount,
        refund_id=order.refund_id,
        refund_time=order.refund_time,
        refund_status=order.refund_status,
    )


@router.post("/{booking_id}/pay", response_model=PayResponse)
async def pay_booking(
    booking_id: int,
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
    if _v(order.status) != "pending":
        raise HTTPException(status_code=400, detail="Order is not pending")
    if not current_user.openid:
        raise HTTPException(status_code=400, detail="User openid not available")

    # Verify slot lock is still valid before creating WeChat Pay order
    if _v(slot.status) != "locked" or slot.locked_by != current_user.id:
        raise HTTPException(status_code=409, detail="Slot lock has expired or been taken")
    if slot.locked_at:
        lock_elapsed = (datetime.utcnow() - slot.locked_at).total_seconds()
        if lock_elapsed >= settings.BOOKING_LOCK_TTL_SECONDS:
            raise HTTPException(status_code=409, detail="Slot lock has expired")

    # Idempotency: reuse existing prepay_id if still fresh
    now = datetime.utcnow()
    if order.prepay_id and order.prepay_id_created_at:
        age = (now - order.prepay_id_created_at).total_seconds()
        if age < settings.PREPAY_ID_TTL_SECONDS:
            wxpay = get_wxpay()
            return build_jsapi_params(wxpay, order.prepay_id)

    # Load venue/club info for description
    venue_result = await db.execute(select(Venue).where(Venue.id == order.venue_id))
    venue = venue_result.scalar_one_or_none()
    description = venue.name if venue else "场地预约"

    wxpay = get_wxpay()
    try:
        result = wxpay.pay(
            description=description,
            out_trade_no=order.order_no,
            amount={"total": _to_cents(order.amount)},
            payer={"openid": current_user.openid},
        )
        prepay_id = result.get("prepay_id")
        if not prepay_id:
            raise HTTPException(status_code=500, detail="WeChat pay did not return prepay_id")

        order.prepay_id = prepay_id
        order.prepay_id_created_at = now
        await db.commit()

        return build_jsapi_params(wxpay, prepay_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WeChat pay order creation failed: {str(e)}")


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
    if not timestamp or abs(now - int(timestamp)) > 300:
        logger.warning("Callback timestamp invalid: timestamp=%s now=%s", timestamp, now)
        raise HTTPException(status_code=400, detail="Callback timestamp invalid")

    if not nonce:
        logger.warning("Callback missing nonce")
        raise HTTPException(status_code=400, detail="Callback nonce missing")

    redis = redis_client
    nonce_key = f"wx:callback:nonce:{nonce}"
    if await redis.get(nonce_key):
        logger.warning("Duplicate callback nonce: %s", nonce)
        raise HTTPException(status_code=400, detail="Duplicate callback nonce")
    await redis.setex(nonce_key, 3600, "1")

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
    result = await db.execute(
        select(BookingOrder, VenueTimeSlot)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == booking_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, slot = row

    # Authorization: booking owner, club admin, or platform admin
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
                raise HTTPException(status_code=403, detail="Not your booking")
        else:
            raise HTTPException(status_code=403, detail="Not your booking")

    if _v(order.status) not in ("pending", "paid"):
        raise HTTPException(status_code=400, detail="Cannot cancel in current status")

    # Calculate refund using Asia/Shanghai local time
    tz = ZoneInfo("Asia/Shanghai")
    now_aware = datetime.now(tz)
    now = now_aware.astimezone(timezone.utc).replace(tzinfo=None)
    slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz)
    hours_before = (slot_datetime - now_aware).total_seconds() / 3600

    if hours_before >= settings.FREE_CANCEL_HOURS:
        refund_amount = order.amount
    elif hours_before >= 0:
        refund_amount = order.amount * Decimal("0.5")
    else:
        raise HTTPException(status_code=400, detail="Cannot cancel after start time")

    order.cancel_reason = req.reason
    order.cancel_time = now
    order.refund_amount = refund_amount

    # If paid, trigger WeChat refund first; only release slot once WeChat confirms SUCCESS callback
    if _v(order.status) == "paid" and refund_amount > 0:
        if not order.wx_transaction_id:
            raise HTTPException(status_code=400, detail="Missing WeChat transaction id")

        wxpay = get_wxpay()
        out_refund_no = _generate_order_no()

        # Create refund record BEFORE calling WeChat (pre-creation for idempotency)
        refund_record = RefundRecord(
            order_id=order.id,
            out_refund_no=out_refund_no,
            amount=refund_amount,
            reason=req.reason or "用户取消订单",
            status="pending",
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
                reason=req.reason or "用户取消订单",
            )
        except Exception as e:
            if _is_refund_retryable(e):
                # Retryable failure: schedule retry
                refund_record.status = "failed"
                refund_record.scheduled_at = datetime.utcnow() + timedelta(seconds=_refund_backoff_seconds(0))
                refund_record.fail_reason = str(e)[:512]
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
            raise HTTPException(status_code=502, detail=f"Refund request failed: {str(e)}")

        order.status = OrderStatus.refunding
        order.refund_id = out_refund_no
        order.refund_status = "pending"
        # Slot stays booked until REFUND.SUCCESS callback arrives
        await db.commit()
    else:
        # Pending order: cancel immediately and release slot
        order.status = OrderStatus.cancelled
        slot.status = SlotStatus.available
        slot.locked_by = None
        slot.locked_at = None
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key, str(order.user_id))
        await db.commit()

    return {"msg": "ok", "refund_amount": str(refund_amount)}


async def _refund_slot_release(slot: VenueTimeSlot, user_id: int):
    """Release a slot when a refund is accepted by WeChat."""
    slot.status = SlotStatus.available
    slot.locked_by = None
    slot.locked_at = None
    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
    await release_lock(lock_key, str(user_id))


@router.post("/{booking_id}/refund")
async def refund_booking(
    booking_id: int,
    req: RefundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refund a paid booking order via WeChat Pay V3 (club/platform admin only)."""
    result = await db.execute(
        select(BookingOrder, VenueTimeSlot)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == booking_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, slot = row

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
        status="pending",
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
            refund_record.status = "failed"
            refund_record.scheduled_at = datetime.utcnow() + timedelta(seconds=_refund_backoff_seconds(0))
            refund_record.fail_reason = str(e)[:512]
            order.refund_status = "failed"
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
    order.refund_status = "pending"
    order.cancel_reason = req.reason or "管理员退款"
    order.cancel_time = datetime.utcnow()

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
            amount=order.amount, status=_v(order.status), payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, prepay_id=order.prepay_id,
            prepay_id_created_at=order.prepay_id_created_at, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end,
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
    if _v(rec.status) == "processing":
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
