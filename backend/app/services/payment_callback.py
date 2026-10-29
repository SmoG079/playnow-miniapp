import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logger import get_logger
from app.core.config import get_settings
from app.core.redis import release_lock
from app.services.booking_locks import lock_owner, locked_order_slots, release_order_slots
from app.api.deps import _v
from app.models.models import (
    User, UserRole, VenueTimeSlot, SlotStatus, BookingOrder, OrderStatus,
    SettlementRecord, SettlementStatus, Notification, NotificationType, Club,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, PaymentLog,
)
from app.services.settlement import generate_settlement_out_order_no, _to_cents

logger = get_logger(__name__)
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

    if order.business_type == "post":
        from app.services.post_payments import payment_success
        return await payment_success(db, data)

    if order.business_type == "tournament":
        from app.services.tournament_lifecycle import payment_success
        return await payment_success(db, data)

    order = (await db.execute(select(BookingOrder).where(BookingOrder.id == order.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()

    # Validate callback amount matches order amount
    callback_total = data.get("amount", {}).get("total")
    expected_total = _to_cents(order.amount)
    if callback_total != expected_total or not transaction_id or transaction_id.startswith("dev_"):
        logger.error("Amount mismatch: callback=%s expected=%s", callback_total, expected_total)
        return {"code": "FAIL", "message": "Amount mismatch"}

    # Cancelled orders can still receive their first real success notification.
    if _v(order.status) in ("paid", "refunding", "refunded", "completed"):
        if order.wx_transaction_id != transaction_id:
            return {"code": "FAIL", "message": "Transaction mismatch"}
        return {"code": "SUCCESS"}
    was_cancelled = _v(order.status) == "cancelled"

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
        slots = await locked_order_slots(db, order)
        expected_ids = order.slot_ids
        expired = order.created_at is None or datetime.utcnow() >= order.created_at + timedelta(seconds=settings.BOOKING_LOCK_TTL_SECONDS)
        anomaly = was_cancelled or expired or not slots or {slot.id for slot in slots} != set(expected_ids)
        anomaly = anomaly or any(slot.booking_order_id != order.id or _v(slot.status) != "locked"
            or slot.locked_by != order.user_id
            or datetime.combine(slot.date, slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai")) <= datetime.now(ZoneInfo("Asia/Shanghai"))
            for slot in slots)
        if anomaly:
            from app.services.booking_refunds import queue_refund
            await queue_refund(db, order, order.amount, "预约名额已失效，支付原路退回")
            await release_order_slots(db, order)
            db.add(Notification(user_id=order.user_id, type=NotificationType.booking,
                title="预约支付异常", content=f"订单 {order.order_no} 已收款但预约失效，已申请原路退款，请查看退款进度",
                ref_id=order.id, ref_type="booking"))
            return {"code": "SUCCESS"}
        for slot in slots:
            slot.status = SlotStatus.booked
            slot.locked_by = None
            slot.locked_at = None
            await release_lock(f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}", lock_owner(order.order_no))

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

    if out_trade_no:
        business = (await db.execute(select(BookingOrder.business_type).where(BookingOrder.order_no == out_trade_no))).scalar_one_or_none()
        if business == "post":
            from app.services.post_payments import refund_callback
            return await refund_callback(db, data)
        if business == "tournament":
            from app.services.tournament_lifecycle import refund_callback
            return await refund_callback(db, data)

    ref = (await db.execute(select(RefundRecord.id, RefundRecord.order_id)
        .where(RefundRecord.out_refund_no == out_refund_no))).first()
    order_id = ref.order_id if ref else await db.scalar(select(BookingOrder.id).where(BookingOrder.order_no == out_trade_no))
    if order_id is None:
        return {"code": "FAIL", "message": "Refund order not found"}
    order = (await db.execute(select(BookingOrder).where(BookingOrder.id == order_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    refund_record = (await db.execute(select(RefundRecord).where(RefundRecord.out_refund_no == out_refund_no)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if out_trade_no != order.order_no:
        return {"code": "FAIL", "message": "Refund order mismatch"}
    if refund_record and refund_record.order_id != order.id:
        return {"code": "FAIL", "message": "Refund intent mismatch"}
    amount = data.get("amount", {})
    if not refund_record:
        # Preserve signed historical/merchant-console refund notifications.
        # Recheck under the order lock and require the actual refunded amount.
        cents = amount.get("refund")
        if not isinstance(cents, int) or not 0 < cents <= _to_cents(order.amount):
            return {"code": "FAIL", "message": "Missing or invalid refund amount"}
        refund_record = RefundRecord(order_id=order.id, out_refund_no=out_refund_no,
            amount=Decimal(cents) / 100, reason="微信退款通知补记", status="pending", retry_count=0)
        db.add(refund_record)
        await db.flush()
    if "refund" in amount and amount["refund"] != _to_cents(refund_record.amount):
        return {"code": "FAIL", "message": "Refund amount mismatch"}
    state = (refund_status or "").lower()
    if state not in ("success", "processing", "closed", "abnormal"):
        return {"code": "FAIL", "message": "Unknown refund status"}
    if _v(refund_record.status) == "success" or (_v(refund_record.status) == state and state in ("closed", "abnormal")):
        return {"code": "SUCCESS"}
    refund_record.status = state
    refund_record.wx_refund_id = wx_refund_id or refund_record.wx_refund_id
    order.refund_id = refund_record.out_refund_no
    order.refund_amount = refund_record.amount
    order.refund_status = state
    if state == "success":
        refund_record.completed_at = datetime.utcnow()
        was_refunded = _v(order.status) == "refunded"
        order.status = OrderStatus.refunded
        order.refund_time = datetime.utcnow()
        await release_order_slots(db, order)
        if not was_refunded:
            db.add(Notification(user_id=order.user_id, type=NotificationType.booking,
                title="退款成功", content=f"您的订单 {order.order_no} 退款已成功到账",
                ref_id=order.id, ref_type="booking"))
    else:
        order.status = OrderStatus.refunding
        if state in ("closed", "abnormal"):
            refund_record.completed_at = datetime.utcnow()
            admins = (await db.scalars(select(User).where(User.role == UserRole.platform_admin))).all()
            for admin in admins:
                db.add(Notification(user_id=admin.id, type=NotificationType.system,
                    title="退款需人工处理", content=f"订单 {order.order_no} 退款{state}，请核对商户平台原单",
                    ref_id=order.id, ref_type="booking"))
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

    if order.business_type == "post":
        from app.services.post_payments import payment_closed
        return await payment_closed(db, data)

    if order.business_type == "tournament":
        from app.services.tournament_lifecycle import payment_closed
        return await payment_closed(db, data)

    order = (await db.execute(select(BookingOrder).where(BookingOrder.id == order.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if _v(order.status) != "pending":
        return {"code": "SUCCESS"}
    order.status = OrderStatus.cancelled
    await release_order_slots(db, order)

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
