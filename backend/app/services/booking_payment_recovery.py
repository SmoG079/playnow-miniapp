"""Recover real booking payments and close cancelled WeChat orders."""
import asyncio
from datetime import datetime
from sqlalchemy import select, or_, update
from app.api.deps import _v
from app.core.logger import get_logger
from app.core.config import get_settings
from app.core.wechat_pay import get_wxpay, wx_request, WeChatPayError
from app.models.models import BookingOrder, PaymentLog
from app.services.payment_callback import _handle_payment_success

logger = get_logger(__name__)


async def maintain(db):
    if not get_settings().WX_PAY_ENABLED:
        return {"processed": 0, "errors": 0}
    rows = (await db.execute(select(BookingOrder.id).where(
        BookingOrder.business_type == "booking",
        BookingOrder.status.in_(["pending", "cancelled"]),
        or_(BookingOrder.prepay_id.isnot(None), select(PaymentLog.id).where(
            PaymentLog.order_id == BookingOrder.id, PaymentLog.event_type == "PREPAY_REQUESTED").exists()))
        .order_by(BookingOrder.updated_at, BookingOrder.id).limit(100))).scalars().all()
    await db.rollback()
    processed = errors = 0
    for ident in rows:
        order = None
        try:
            order = (await db.execute(select(BookingOrder).where(BookingOrder.id == ident)
                .with_for_update().execution_options(populate_existing=True))).scalar_one()
            if _v(order.status) not in ("pending", "cancelled"):
                await db.rollback()
                continue
            order.updated_at = datetime.utcnow()
            wxpay = get_wxpay()
            try:
                data = await asyncio.to_thread(wx_request, wxpay, "query", out_trade_no=order.order_no)
            except WeChatPayError as exc:
                if exc.payload.get("code") != "ORDER_NOT_EXIST":
                    raise
                data = {"trade_state": "CLOSED"}
            state = data.get("trade_state")
            if state == "SUCCESS":
                if data.get("out_trade_no") != order.order_no:
                    raise RuntimeError("Payment query identity mismatch")
                outcome = await _handle_payment_success(data, db)
                if outcome.get("code") != "SUCCESS":
                    raise RuntimeError("Payment query mismatch")
            elif _v(order.status) == "cancelled":
                if state not in ("CLOSED", "REVOKED"):
                    await asyncio.to_thread(wx_request, wxpay, "close", out_trade_no=order.order_no)
                order.prepay_id = None
                await db.execute(update(PaymentLog).where(PaymentLog.order_id == order.id,
                    PaymentLog.event_type == "PREPAY_REQUESTED").values(event_type="PREPAY_CLOSED"))
            await db.commit()
            processed += 1
        except Exception:
            await db.rollback()
            # Persist the attempt to avoid starving later orders on repeated errors.
            await db.execute(update(BookingOrder).where(BookingOrder.id == ident)
                .values(updated_at=datetime.utcnow()))
            await db.commit()
            logger.error("Booking payment recovery failed: order=%s", ident, exc_info=True)
            errors += 1
    return {"processed": processed, "errors": errors}
