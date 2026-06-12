import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis import acquire_lock, release_lock
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.api.deps import get_current_user, get_club_admin, get_platform_admin, _v
from app.models.models import (
    User, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    SettlementRecord, Notification, NotificationType, Club, ClubMember,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, PaymentLog,
)
from app.schemas.schemas import (
    BookingCreateRequest, BookingDetail, BookingListParams, PayResponse,
    CancelRequest, RefundRequest, PaginatedResponse,
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
    """Lock a slot and create a pending booking order."""
    # Get slot
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == req.slot_id)
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if _v(slot.status) != "available":
        raise HTTPException(status_code=409, detail="Slot is not available")

    # Get venue + club
    venue_result = await db.execute(select(Venue).where(Venue.id == slot.venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue or _v(venue.status) != "active":
        raise HTTPException(status_code=400, detail="Venue not available")

    club_result = await db.execute(select(Club).where(Club.id == venue.club_id))
    club = club_result.scalar_one_or_none()

    # Try Redis lock
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
        select(BookingOrder).where(BookingOrder.id == booking_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if order.status != OrderStatus.pending:
        raise HTTPException(status_code=400, detail="Order is not pending")
    if not current_user.openid:
        raise HTTPException(status_code=400, detail="User openid not available")

    # Load venue/club info for description
    venue_result = await db.execute(select(Venue).where(Venue.id == order.venue_id))
    venue = venue_result.scalar_one_or_none()
    description = venue.name if venue else "场地预约"

    wxpay = get_wxpay()
    try:
        result = wxpay.pay(
            description=description,
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


@router.post("/wx-notify")
async def wx_pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """WeChat payment callback. Handles both payment success and refund notifications."""
    body = await request.body()

    # Parse outer notification envelope first to get event_type
    try:
        notification = json.loads(body)
    except json.JSONDecodeError:
        return {"code": "FAIL", "message": "Invalid callback payload"}

    event_type = notification.get("event_type", "")

    try:
        wxpay = get_wxpay()
        decrypted = wxpay.decrypt_callback(request.headers, body)
    except Exception as e:
        return {"code": "FAIL", "message": f"Signature verification failed: {str(e)}"}

    if not decrypted:
        return {"code": "FAIL", "message": "Invalid callback signature or decryption failed"}

    try:
        data = json.loads(decrypted)
    except json.JSONDecodeError:
        return {"code": "FAIL", "message": "Invalid callback payload"}

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
        raw_data={"notification": notification, "resource": data},
    )
    db.add(log)

    try:
        # Handle refund callbacks
        if event_type.startswith("REFUND."):
            return await _handle_refund_callback(data, db)

        # Handle payment callbacks
        if event_type == "TRANSACTION.SUCCESS":
            return await _handle_payment_success(data, db)

        if event_type == "TRANSACTION.CLOSED":
            return await _handle_payment_closed(data, db)

        # Other events - acknowledge but no action needed
        await db.commit()
        return {"code": "SUCCESS"}
    except Exception as e:
        await db.rollback()
        # Always return a valid WeChat response; rely on WeChat retry for real failures
        return {"code": "FAIL", "message": f"Internal error: {str(e)}"}


async def _handle_payment_success(data: dict, db: AsyncSession):
    """Handle TRANSACTION.SUCCESS callback."""
    out_trade_no = data.get("out_trade_no")
    transaction_id = data.get("transaction_id")

    if not out_trade_no:
        return {"code": "FAIL", "message": "Missing out_trade_no"}

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    if not order:
        return {"code": "FAIL", "message": "Order not found"}

    # Idempotency: skip terminal states (asyncmy returns enums as strings)
    if _v(order.status) in ("paid", "refunding", "refunded", "cancelled"):
        return {"code": "SUCCESS"}

    order.status = OrderStatus.paid
    order.payment_time = datetime.utcnow()
    order.wx_transaction_id = transaction_id

    # Handle tournament registration payment
    tournament_reg_result = await db.execute(
        select(TournamentRegistration).where(TournamentRegistration.order_id == order.id)
    )
    tournament_reg = tournament_reg_result.scalar_one_or_none()
    if tournament_reg:
        tournament_reg.status = TournamentRegStatus.confirmed
        tournament = await db.execute(
            select(Tournament).where(Tournament.id == tournament_reg.tournament_id)
        )
        tournament = tournament.scalar_one_or_none()
        if tournament:
            tournament.current_participants = (tournament.current_participants or 0) + 1
        notif = Notification(
            user_id=order.user_id,
            type=NotificationType.tournament,
            title="赛事报名成功",
            content=f"您已成功报名赛事，订单号 {order.order_no}",
            ref_id=tournament_reg.id,
            ref_type="tournament_registration",
        )
        db.add(notif)
    else:
        # Mark slot as booked
        slot_result = await db.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
        )
        slot = slot_result.scalar_one_or_none()
        if slot:
            slot.status = SlotStatus.booked
            lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
            await release_lock(lock_key, str(order.user_id))

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
            status=SettlementStatus.pending,
        )
        db.add(settlement)

        notif = Notification(
            user_id=order.user_id,
            type=NotificationType.booking,
            title="预约成功",
            content=f"您的场地预约已支付成功，订单号 {order.order_no}",
            ref_id=order.id,
            ref_type="booking",
        )
        db.add(notif)

    await db.commit()
    return {"code": "SUCCESS"}


async def _handle_refund_callback(data: dict, db: AsyncSession):
    """Handle REFUND.* callbacks."""
    out_refund_no = data.get("out_refund_no")
    out_trade_no = data.get("out_trade_no")
    refund_status = data.get("refund_status")
    wx_refund_id = data.get("refund_id")

    if not out_refund_no:
        return {"code": "FAIL", "message": "Missing out_refund_no"}

    # Find refund record
    result = await db.execute(
        select(RefundRecord).where(RefundRecord.out_refund_no == out_refund_no)
    )
    refund_record = result.scalar_one_or_none()

    if not refund_record:
        # Try to find by order
        if out_trade_no:
            order_result = await db.execute(
                select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
            )
            order = order_result.scalar_one_or_none()
            if order:
                # Create refund record retroactively using actual amount from callback if available
                actual_refund_cents = data.get("amount", {}).get("refund")
                actual_refund = Decimal(actual_refund_cents) / Decimal(100) if actual_refund_cents is not None else (order.refund_amount or order.amount)
                refund_record = RefundRecord(
                    order_id=order.id,
                    out_refund_no=out_refund_no,
                    wx_refund_id=wx_refund_id,
                    amount=actual_refund,
                    reason=order.cancel_reason or "用户退款",
                    status="pending",
                )
                db.add(refund_record)

    if refund_status == "SUCCESS":
        if refund_record:
            refund_record.status = "success"
            refund_record.wx_refund_id = wx_refund_id
            refund_record.completed_at = datetime.utcnow()

        # Update order status
        if out_trade_no:
            order_result = await db.execute(
                select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
            )
            order = order_result.scalar_one_or_none()
            if not order:
                await db.commit()
                return {"code": "SUCCESS"}

            # Idempotency: do nothing if already refunded
            if _v(order.status) == "refunded":
                await db.commit()
                return {"code": "SUCCESS"}

            if _v(order.status) == "refunding":
                order.status = OrderStatus.refunded
                order.refund_time = datetime.utcnow()
                order.refund_status = "success"

                # Release slot
                slot_result = await db.execute(
                    select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
                )
                slot = slot_result.scalar_one_or_none()
                if slot:
                    slot.status = SlotStatus.available
                    slot.locked_by = None
                    slot.locked_at = None
                    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
                    await release_lock(lock_key, str(order.user_id))

                # Notify user
                notif = Notification(
                    user_id=order.user_id,
                    type=NotificationType.booking,
                    title="退款成功",
                    content=f"您的订单 {order.order_no} 退款已成功到账",
                    ref_id=order.id,
                    ref_type="booking",
                )
                db.add(notif)

    elif refund_status == "CLOSED":
        if refund_record:
            refund_record.status = "closed"
        if out_trade_no:
            order_result = await db.execute(
                select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.refund_status = "closed"
                # Revert to paid if refund closed and reclaim slot
                if _v(order.status) == "refunding":
                    order.status = OrderStatus.paid
                    slot_result = await db.execute(
                        select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
                    )
                    slot = slot_result.scalar_one_or_none()
                    if slot:
                        # Only reclaim if the slot is still available; otherwise leave it booked by someone else
                        if slot.status == SlotStatus.available:
                            slot.status = SlotStatus.booked
                            slot.locked_by = order.user_id
                            slot.locked_at = datetime.utcnow()
                            lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
                            acquired = await acquire_lock(lock_key, str(order.user_id), settings.BOOKING_LOCK_TTL_SECONDS)
                            if not acquired:
                                # Lock contention: another booking may be in progress; leave slot available and log
                                slot.status = SlotStatus.available
                                slot.locked_by = None
                                slot.locked_at = None

    await db.commit()
    return {"code": "SUCCESS"}


async def _handle_payment_closed(data: dict, db: AsyncSession):
    """Handle TRANSACTION.CLOSED callback (order closed without payment)."""
    out_trade_no = data.get("out_trade_no")
    if not out_trade_no:
        return {"code": "FAIL", "message": "Missing out_trade_no"}

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    if not order:
        return {"code": "SUCCESS"}

    if _v(order.status) in ("cancelled", "paid", "refunding", "refunded"):
        await db.commit()
        return {"code": "SUCCESS"}

    order.status = OrderStatus.cancelled

    slot_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
    )
    slot = slot_result.scalar_one_or_none()
    if slot:
        slot.status = SlotStatus.available
        slot.locked_by = None
        slot.locked_at = None
        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
        await release_lock(lock_key, str(order.user_id))

    await db.commit()
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

    order.cancel_reason = req.reason
    order.cancel_time = now
    order.refund_amount = refund_amount

    # If paid, trigger WeChat refund first; only release slot once WeChat confirms SUCCESS callback
    if _v(order.status) == "paid" and refund_amount > 0:
        if not order.wx_transaction_id:
            raise HTTPException(status_code=400, detail="Missing WeChat transaction id")

        wxpay = get_wxpay()
        out_refund_no = _generate_order_no()
        try:
            wxpay.refund(
                out_refund_no=out_refund_no,
                transaction_id=order.wx_transaction_id,
                amount={
                    "refund": int(refund_amount * 100),
                    "total": int(order.amount * 100),
                    "currency": "CNY",
                },
                reason=req.reason or "用户取消订单",
            )
        except Exception as e:
            # Refund API failed; record failure and keep order paid/slot reserved
            order.refund_status = "failed"
            await db.commit()
            raise HTTPException(status_code=502, detail=f"Refund request failed: {str(e)}")

        order.status = OrderStatus.refunding
        order.refund_id = out_refund_no
        order.refund_status = "pending"

        # Create refund record
        refund_record = RefundRecord(
            order_id=order.id,
            out_refund_no=out_refund_no,
            amount=refund_amount,
            reason=req.reason or "用户取消订单",
            status="pending",
        )
        db.add(refund_record)
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
    try:
        wxpay.refund(
            out_refund_no=out_refund_no,
            transaction_id=order.wx_transaction_id,
            amount={
                "refund": int(refund_amount * 100),
                "total": int(order.amount * 100),
                "currency": "CNY",
            },
            reason=req.reason or "管理员退款",
        )
    except Exception as e:
        order.refund_status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"WeChat refund failed: {str(e)}")

    order.status = OrderStatus.refunding
    order.refund_amount = refund_amount
    order.refund_id = out_refund_no
    order.refund_status = "pending"
    order.cancel_reason = req.reason or "管理员退款"
    order.cancel_time = datetime.utcnow()

    # Create refund record
    refund_record = RefundRecord(
        order_id=order.id,
        out_refund_no=out_refund_no,
        amount=refund_amount,
        reason=req.reason or "管理员退款",
        status="pending",
    )
    db.add(refund_record)

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
            wx_transaction_id=order.wx_transaction_id, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end,
            refund_amount=order.refund_amount, refund_id=order.refund_id,
            refund_time=order.refund_time, refund_status=order.refund_status,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
