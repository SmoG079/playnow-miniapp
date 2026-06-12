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
from app.api.deps import get_current_user, get_club_admin, _v
from app.models.models import (
    User, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    SettlementRecord, Notification, NotificationType, Club, ClubMember,
    TournamentRegistration, TournamentRegStatus,
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
    """Lock a slot and create a pending booking order."""
    # Get slot
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id == req.slot_id)
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.status != SlotStatus.available:
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
    """WeChat payment callback. Verify signature, decrypt payload, and update order status."""
    body = await request.body()

    try:
        wxpay = get_wxpay()
        decrypted = wxpay.decrypt_callback(request.headers, body)
    except Exception as e:
        # Signature verification failed, decryption error, or missing certificate
        return {"code": "FAIL", "message": f"Signature verification failed: {str(e)}"}

    if not decrypted:
        return {"code": "FAIL", "message": "Invalid callback signature or decryption failed"}

    try:
        data = json.loads(decrypted)
    except json.JSONDecodeError:
        return {"code": "FAIL", "message": "Invalid callback payload"}

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

    # Idempotency check
    if order.status == OrderStatus.paid:
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
        # Create notification for tournament registration
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

    # Release slot
    slot.status = SlotStatus.available
    slot.locked_by = None
    slot.locked_at = None
    lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
    await release_lock(lock_key, str(order.user_id))

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
            amount=order.amount, status=_v(order.status), payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
