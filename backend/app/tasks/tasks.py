import asyncio
import logging
from datetime import datetime, timezone, date, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, delete
from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.redis import release_lock
from app.api.deps import _v
from app.models.models import (
    BookingOrder,
    OrderStatus,
    RefundRecord,
    SettlementRecord,
    SettlementStatus,
    SlotStatus,
    VenueTimeSlot,
)
from app.services.payment_callback import process_callback
from app.services.settlement import _to_cents
from app.tasks.worker import celery_app
from app.tasks.runtime import run_async_task, task_session_factory

logger = logging.getLogger(__name__)


async def _release_expired_locks_impl():
    from app.services.booking_locks import release_order_slots
    async with (task_session_factory.get() or async_session_factory)() as session:
        cutoff = datetime.utcnow() - timedelta(seconds=get_settings().BOOKING_LOCK_TTL_SECONDS)
        ids = (await session.execute(select(BookingOrder.id).where(
            BookingOrder.business_type == "booking", BookingOrder.status == OrderStatus.pending,
            BookingOrder.created_at <= cutoff).order_by(BookingOrder.id))).scalars().all()
        released = 0
        for ident in ids:
            order = (await session.execute(select(BookingOrder).where(BookingOrder.id == ident)
                .with_for_update().execution_options(populate_existing=True))).scalar_one()
            if _v(order.status) != "pending" or order.created_at > cutoff:
                continue
            slots = await release_order_slots(session, order)
            released += len(slots)
            order.status = OrderStatus.cancelled
            order.cancel_reason = "Payment timeout"
            order.cancel_time = datetime.utcnow()
        await session.commit()
        return released


@celery_app.task(name="app.tasks.tasks.release_expired_locks")
def release_expired_locks():
    released = run_async_task(_release_expired_locks_impl)
    return f"Released {released} expired locks"


async def _generate_daily_slots_impl():
    from app.models.models import Venue, VenueStatus
    from app.services.slots import ensure_slots
    async with (task_session_factory.get() or async_session_factory)() as session:
        venues = (await session.execute(select(Venue.id).where(Venue.status == VenueStatus.active)
            .order_by(Venue.id))).scalars().all()
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        total = 0
        for ident in venues:
            for offset in range(3):
                created, _ = await ensure_slots(session, ident, today + timedelta(days=offset))
                total += created
        await session.commit()
        return total


async def _cleanup_old_slots_impl():
    """Delete available slots older than 30 days (not referenced by bookings)."""
    async with (task_session_factory.get() or async_session_factory)() as session:
        cutoff = datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=30)
        result = await session.execute(
            select(VenueTimeSlot.id).where(
                VenueTimeSlot.status == SlotStatus.available,
                VenueTimeSlot.date < cutoff,
            )
        )
        ids = [r[0] for r in result.all()]
        if not ids:
            return 0
        # JSON slot_ids has no foreign key: protect every slot in historical
        # orders, including cancelled orders and legacy single-slot bookings.
        referenced = set()
        orders = await session.stream(select(BookingOrder.slot_id, BookingOrder.slot_ids))
        async for slot_id, slot_ids in orders:
            if slot_id is not None:
                referenced.add(slot_id)
            referenced.update(slot_ids or [])
        from app.models.models import BookingSlot
        detail_ids = await session.stream(select(BookingSlot.slot_id))
        async for row in detail_ids:
            referenced.add(row[0])
        ids = [slot_id for slot_id in ids if slot_id not in referenced]
        # Delete in batches of 1000
        count = 0
        for i in range(0, len(ids), 1000):
            batch = ids[i:i+1000]
            await session.execute(delete(VenueTimeSlot).where(VenueTimeSlot.id.in_(batch)))
            count += len(batch)
        await session.commit()
        return count


@celery_app.task(name="app.tasks.tasks.cleanup_old_slots")
def cleanup_old_slots():
    count = run_async_task(_cleanup_old_slots_impl)
    return f"Cleaned up {count} old slots"


@celery_app.task(name="app.tasks.tasks.generate_daily_slots")
def generate_daily_slots():
    created = run_async_task(_generate_daily_slots_impl)
    return f"Generated {created} slots"


async def _execute_pending_settlements_impl():
    """Poll for due pending settlements and execute profit-sharing."""
    from app.services.settlement import execute_settlement, query_settlement_status

    settings = get_settings()
    if not settings.PROFIT_SHARING_ENABLED:
        # 平台用自有商户号直接收款，暂不分账。SettlementRecord 只作记账留存，
        # 不向微信发起分账请求。 见 docs/wechat-pay-setup.md
        return {"processed": 0, "errors": 0, "skipped": "profit_sharing_disabled"}

    async with (task_session_factory.get() or async_session_factory)() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(SettlementRecord.id)
            .where(
                SettlementRecord.status.in_([SettlementStatus.pending, SettlementStatus.failed]),
                SettlementRecord.scheduled_at <= now,
                SettlementRecord.retry_count < settings.SETTLEMENT_MAX_RETRIES,
            )
            .order_by(SettlementRecord.scheduled_at)
            .limit(settings.SETTLEMENT_BATCH_SIZE)
        )
        ids = [r[0] for r in result.all()]

        processed = 0
        errors = 0
        for sid in ids:
            try:
                rec = await execute_settlement(session, sid)
                await session.commit()  # persist processing state / wx_split_order_no
                if rec.status == SettlementStatus.processing and rec.wx_split_order_no:
                    try:
                        await query_settlement_status(session, sid)
                        await session.commit()
                    except Exception:
                        logger.exception("Settlement %s query status failed, but processing state is committed", sid)
                processed += 1
            except Exception:
                logger.exception("Settlement %s failed during batch execution", sid)
                await session.rollback()
                errors += 1

        return {"processed": processed, "errors": errors}


@celery_app.task(name="app.tasks.tasks.execute_pending_settlements")
def execute_pending_settlements():
    return run_async_task(_execute_pending_settlements_impl)


def _refund_backoff_seconds(attempt: int) -> int:
    settings = get_settings()
    base = settings.REFUND_RETRY_BACKOFF_BASE_SECONDS
    return min(base * (2 ** attempt), 1800)


async def _recover_booking_refunds_impl(*, processing=False):
    from app.core.wechat_pay import WeChatPayError, get_wxpay, wx_request
    settings = get_settings()
    async with (task_session_factory.get() or async_session_factory)() as session:
        now = datetime.utcnow()
        query = select(RefundRecord.id, RefundRecord.order_id).join(BookingOrder).where(
            BookingOrder.business_type != "tournament")
        if processing:
            query = query.where(RefundRecord.status == "processing",
                RefundRecord.updated_at <= now - timedelta(minutes=1))
        else:
            query = query.where(RefundRecord.status.in_(["pending", "failed"]),
                RefundRecord.scheduled_at <= now,
                RefundRecord.retry_count < settings.REFUND_MAX_RETRIES)
        rows = (await session.execute(query.order_by(RefundRecord.updated_at, RefundRecord.id)
            .limit(settings.REFUND_BATCH_SIZE))).all()
        await session.rollback()
        processed = errors = 0
        for ident, order_id in rows:
            rec = None
            transition_started = False
            try:
                # Lock before reading state or calling WeChat. Callbacks and
                # administrator requests use this same order -> refund ordering.
                order = (await session.execute(select(BookingOrder).where(BookingOrder.id == order_id)
                    .with_for_update().execution_options(populate_existing=True))).scalar_one()
                rec = (await session.execute(select(RefundRecord).where(RefundRecord.id == ident)
                    .with_for_update().execution_options(populate_existing=True))).scalar_one()
                if _v(rec.status) not in (("processing",) if processing else ("pending", "failed")):
                    await session.rollback()
                    continue
                if not processing and (rec.retry_count >= settings.REFUND_MAX_RETRIES
                    or not rec.scheduled_at or rec.scheduled_at > datetime.utcnow()):
                    await session.rollback()
                    continue
                if not order.wx_transaction_id or order.wx_transaction_id.startswith("dev_"):
                    raise RuntimeError("Unverified booking payment")
                # Heal snapshots left by old timeout branches without minting a new number.
                order.refund_id, order.refund_amount = rec.out_refund_no, rec.amount
                order.status = OrderStatus.refunding
                rec.updated_at = datetime.utcnow()
                wxpay = get_wxpay()
                try:
                    response = await asyncio.to_thread(wx_request, wxpay, "query_refund", out_refund_no=rec.out_refund_no)
                except WeChatPayError as exc:
                    if processing or exc.status != 404 or exc.payload.get("code") != "RESOURCE_NOT_EXISTS":
                        raise
                    response = None
                if response is None:
                    response = await asyncio.to_thread(wx_request, wxpay, "refund",
                        out_refund_no=rec.out_refund_no, transaction_id=order.wx_transaction_id,
                        amount={"refund": _to_cents(rec.amount), "total": _to_cents(order.amount), "currency": "CNY"},
                        reason=rec.reason or "管理员退款")
                state = response.get("status", "").upper()
                if state not in ("SUCCESS", "PROCESSING", "CLOSED", "ABNORMAL"):
                    raise RuntimeError("Unknown refund status")
                if response.get("out_refund_no") != rec.out_refund_no or response.get("out_trade_no") != order.order_no:
                    raise RuntimeError("Refund response identity mismatch")
                amount = response.get("amount", {})
                if "refund" in amount and amount["refund"] != _to_cents(rec.amount):
                    raise RuntimeError("Refund response amount mismatch")
                from app.services.payment_callback import _handle_refund_callback
                transition_started = True
                outcome = await _handle_refund_callback(dict(response, refund_status=state), session)
                if outcome.get("code") != "SUCCESS":
                    raise RuntimeError("Refund response rejected")
                rec.fail_reason = None
                await session.commit()
                processed += 1
            except Exception as exc:
                # Hold acquired row locks while recording the failed attempt.
                # No rollback/reacquire window in which a success can be overwritten.
                if rec is not None and session.is_active and not transition_started:
                    if _v(rec.status) != "success":
                        if not processing:
                            rec.retry_count += 1
                            rec.scheduled_at = datetime.utcnow() + timedelta(seconds=_refund_backoff_seconds(rec.retry_count))
                            if (isinstance(exc, WeChatPayError) and 400 <= exc.status < 500 and exc.status != 429
                                and exc.payload.get("code") not in ("SYSTEM_ERROR", "BIZERR_NEED_RETRY", "FREQUENCY_LIMITED")):
                                rec.retry_count = settings.REFUND_MAX_RETRIES
                            if rec.retry_count >= settings.REFUND_MAX_RETRIES:
                                rec.status = "failed"
                                order.refund_status = "failed"
                                from app.models.models import Notification, NotificationType
                                session.add(Notification(user_id=order.user_id, type=NotificationType.booking,
                                    title="退款需人工处理", content=f"订单 {order.order_no} 退款结果未确认，请联系管理员核对原单",
                                    ref_id=order.id, ref_type="booking"))
                        rec.fail_reason = "退款结果未确认，请查询原单后重试"
                    await session.commit()
                else:
                    await session.rollback()
                logger.error("Booking refund recovery failed: refund=%s", ident, exc_info=True)
                errors += 1
        return {"processed": processed, "errors": errors}


async def _retry_failed_refunds_impl():
    return await _recover_booking_refunds_impl()


@celery_app.task(name="app.tasks.tasks.retry_failed_refunds")
def retry_failed_refunds():
    return run_async_task(_retry_failed_refunds_impl)


async def _poll_processing_refunds_impl():
    return await _recover_booking_refunds_impl(processing=True)


@celery_app.task(name="app.tasks.tasks.poll_processing_refunds")
def poll_processing_refunds():
    return run_async_task(_poll_processing_refunds_impl)


async def _maintain_booking_payments_impl():
    from app.services.booking_payment_recovery import maintain
    async with (task_session_factory.get() or async_session_factory)() as session:
        return await maintain(session)


@celery_app.task(name="app.tasks.tasks.maintain_booking_payments")
def maintain_booking_payments():
    return run_async_task(_maintain_booking_payments_impl)


async def _process_wx_callback_impl(event_type: str, data: dict):
    """Process WeChat Pay callback asynchronously after immediate acknowledgment."""
    async with (task_session_factory.get() or async_session_factory)() as session:
        try:
            result = await process_callback(event_type, data, session)
            await session.commit()
            return result
        except Exception:
            logger.exception("process_wx_callback failed for event_type=%s", event_type)
            await session.rollback()
            raise


@celery_app.task(name="app.tasks.tasks.process_wx_callback", acks_late=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_wx_callback(event_type: str, data: dict):
    return run_async_task(_process_wx_callback_impl, event_type, data)


@celery_app.task(name="app.tasks.tasks.maintain_tournaments")
def maintain_tournaments():
    from app.services.tournament_maintenance import maintain
    return run_async_task(maintain)


async def _expire_price_rules_impl():
    from app.models.models import Venue, ClubMember, Notification, NotificationType
    from app.services.price_rules import expires_at
    from app.core.logger import get_logger
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    removed = 0
    async with (task_session_factory.get() or async_session_factory)() as session:
        ids = (await session.execute(select(Venue.id).where(Venue.price_rules.is_not(None)).order_by(Venue.id))).scalars().all()
        for ident in ids:
            venue = (await session.execute(select(Venue).where(Venue.id == ident).with_for_update().execution_options(populate_existing=True))).scalar_one()
            expired, kept = [], []
            for rule in venue.price_rules or []:
                expiry = expires_at(rule)
                (expired if expiry and expiry <= now else kept).append(rule)
            if not expired:
                continue
            venue.price_rules = kept
            recipients = (await session.execute(select(ClubMember.user_id).where(ClubMember.club_id == venue.club_id))).scalars().all()
            for user_id in recipients:
                session.add(Notification(user_id=user_id, type=NotificationType.system,
                    title="场地特殊价格规则已到期", content=f"{venue.name} 的 {len(expired)} 条特殊价格规则已到期并自动移除，请查看场地价格设置。",
                    ref_id=venue.id, ref_type="venue"))
            removed += len(expired)
            get_logger(__name__).info("Expired %s price rules for venue %s", len(expired), ident)
        await session.commit()
    return removed


@celery_app.task(name="app.tasks.tasks.expire_price_rules")
def expire_price_rules():
    return run_async_task(_expire_price_rules_impl)
