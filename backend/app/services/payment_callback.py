import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.redis import release_lock
from app.api.deps import _v
from app.models.models import (
    User, UserRole, VenueTimeSlot, SlotStatus, BookingOrder, OrderStatus,
    SettlementRecord, SettlementStatus, Notification, NotificationType, Club,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, PaymentLog,
)
from app.services.settlement import generate_settlement_out_order_no, _to_cents

logger = logging.getLogger(__name__)
settings = get_settings()


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

    # Validate callback amount matches order amount
    callback_total = data.get("amount", {}).get("total")
    expected_total = _to_cents(order.amount)
    if callback_total is not None and callback_total != expected_total:
        logger.error("Amount mismatch: callback=%s expected=%s", callback_total, expected_total)
        return {"code": "FAIL", "message": "Amount mismatch"}

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
            # Verify the slot is still locked by this order's user before marking booked
            if _v(slot.status) != "locked" or slot.locked_by != order.user_id:
                # Lock expired or was taken by another booking; log anomaly and do not change slot state
                notif = Notification(
                    user_id=order.user_id,
                    type=NotificationType.booking,
                    title="预约支付异常",
                    content=f"订单 {order.order_no} 支付成功，但场地锁定已失效，请联系客服处理",
                    ref_id=order.id,
                    ref_type="booking",
                )
                db.add(notif)
                return {"code": "SUCCESS"}
            slot.status = SlotStatus.booked
            slot.locked_by = None
            slot.locked_at = None
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
            out_order_no=generate_settlement_out_order_no(order.order_no),
            scheduled_at=order.payment_time + timedelta(days=settings.SETTLEMENT_DELAY_DAYS),
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
            # Idempotency: only update if not already success
            if _v(refund_record.status) != "success":
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
                return {"code": "SUCCESS"}

            # Idempotency: do nothing if already refunded
            if _v(order.status) == "refunded":
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
                    if _v(slot.status) == "locked" and slot.locked_by == order.user_id:
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
            if _v(refund_record.status) != "closed":
                refund_record.status = "closed"
                refund_record.completed_at = datetime.utcnow()
        if out_trade_no:
            order_result = await db.execute(
                select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.refund_status = "closed"
                # Refund closed: order remains valid, revert to paid. Do not reclaim Redis lock.
                if _v(order.status) == "refunding":
                    order.status = OrderStatus.paid
                    slot_result = await db.execute(
                        select(VenueTimeSlot).where(VenueTimeSlot.id == order.slot_id)
                    )
                    slot = slot_result.scalar_one_or_none()
                    if slot and _v(slot.status) == "available":
                        # Reclaim slot as booked without lock; if someone else booked it, leave as-is
                        slot.status = SlotStatus.booked
                        slot.locked_by = None
                        slot.locked_at = None

    elif refund_status == "ABNORMAL":
        if refund_record:
            if _v(refund_record.status) != "abnormal":
                refund_record.status = "abnormal"
                refund_record.completed_at = datetime.utcnow()
        if out_trade_no:
            order_result = await db.execute(
                select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.refund_status = "abnormal"
                # Refund failed abnormally: user still has valid paid booking
                if _v(order.status) == "refunding":
                    order.status = OrderStatus.paid

                # Notify user
                notif_user = Notification(
                    user_id=order.user_id,
                    type=NotificationType.booking,
                    title="退款异常",
                    content=f"您的订单 {order.order_no} 退款处理异常，请联系客服处理",
                    ref_id=order.id,
                    ref_type="booking",
                )
                db.add(notif_user)

                # Notify platform admins for manual review
                admin_result = await db.execute(
                    select(User).where(User.role == UserRole.platform_admin)
                )
                admins = admin_result.scalars().all()
                for admin in admins:
                    notif_admin = Notification(
                        user_id=admin.id,
                        type=NotificationType.system,
                        title="退款异常需人工处理",
                        content=f"订单 {order.order_no} 退款异常，退款单号 {out_refund_no}",
                        ref_id=order.id,
                        ref_type="booking",
                    )
                    db.add(notif_admin)

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

    return {"code": "SUCCESS"}


async def process_callback(event_type: str, data: dict, db: AsyncSession):
    """Route callback to the appropriate handler based on event_type."""
    if event_type.startswith("REFUND."):
        return await _handle_refund_callback(data, db)
    if event_type == "TRANSACTION.SUCCESS":
        return await _handle_payment_success(data, db)
    if event_type == "TRANSACTION.CLOSED":
        return await _handle_payment_closed(data, db)
    # Other events - acknowledge but no action needed
    return {"code": "SUCCESS"}
