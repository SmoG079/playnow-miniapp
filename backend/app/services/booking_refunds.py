"""Persist one refund intent per booking before any remote request.

Callers hold the order row lock. Remote recovery always takes order -> refund
-> slot locks, and retries reuse the persisted merchant refund number.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.api.deps import _v
from app.core.config import get_settings
from app.models.models import RefundRecord, RefundStatus, OrderStatus, VenueTimeSlot, BookingSlot

BOOKING_CANCEL_CUTOFF = timedelta(hours=1)


async def cancellation_deadline(db, order):
    first = (await db.scalars(select(VenueTimeSlot).join(BookingSlot,
        BookingSlot.slot_id == VenueTimeSlot.id).where(BookingSlot.order_id == order.id)
        .order_by(VenueTimeSlot.date, VenueTimeSlot.start_time).limit(1))).first()
    if first is None:
        raise HTTPException(409, "预约时段无法核验，请联系管理员")
    start = first.start_time
    if isinstance(start, timedelta):
        start = (datetime.min + start).time()
    utc_start = datetime.combine(first.date, start).replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).replace(tzinfo=None)
    return utc_start - BOOKING_CANCEL_CUTOFF


def refund_response(order):
    return {"msg": "ok", "status": _v(order.status),
        "out_refund_no": order.refund_id,
        "refund_amount": str(order.refund_amount) if order.refund_amount is not None else None}


async def dispatch_refund(db, order):
    """Commit the intent before best-effort dispatch; Beat is the fallback."""
    await db.commit()
    if _v(order.status) != "refunded":
        from app.tasks.tasks import retry_failed_refunds
        from app.core.logger import get_logger
        try:
            retry_failed_refunds.delay()
        except Exception:
            get_logger(__name__).error("Refund persisted; immediate dispatch failed: order=%s", order.id, exc_info=True)
    return refund_response(order)


async def queue_refund(db, order, amount, reason, *, retry=False):
    if not order.wx_transaction_id or order.wx_transaction_id.startswith("dev_"):
        raise HTTPException(409, "该订单没有真实微信收款，不能退款")
    records = list((await db.scalars(select(RefundRecord).where(
        RefundRecord.order_id == order.id).order_by(RefundRecord.id)
        .with_for_update().execution_options(populate_existing=True))).all())
    if len(records) > 1:
        raise HTTPException(409, "该订单存在多笔历史退款，请先由管理员核对")
    if records:
        rec = records[0]
        if rec.amount != amount:
            raise HTTPException(409, "该订单已申请退款，不能变更金额或重复申请")
        if _v(rec.status) in ("abnormal", "closed"):
            raise HTTPException(409, "退款异常或已关闭，请在微信商户平台核对处理")
        if retry and _v(rec.status) == "failed" and (rec.retry_count or 0) >= get_settings().REFUND_MAX_RETRIES:
            rec.retry_count = 0
            rec.scheduled_at = datetime.utcnow()
        if _v(rec.status) in ("pending", "failed") and rec.scheduled_at is None:
            rec.scheduled_at = datetime.utcnow()
    else:
        if _v(order.status) == "refunded":
            raise HTTPException(409, "历史订单已退款，请先核对退款记录")
        rec = RefundRecord(order_id=order.id, out_refund_no=f"BR{order.id}",
            amount=amount, reason=reason, status=RefundStatus.pending,
            retry_count=0, scheduled_at=datetime.utcnow())
        db.add(rec)
    order.status = OrderStatus.refunded if _v(rec.status) == "success" else OrderStatus.refunding
    order.refund_amount = rec.amount
    order.refund_id = rec.out_refund_no
    order.refund_status = rec.status
    order.cancel_reason = reason
    order.cancel_time = order.cancel_time or datetime.utcnow()
    await db.flush()
    return rec
