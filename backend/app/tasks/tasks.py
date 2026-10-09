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


def _is_refund_retryable(exc: Exception) -> bool:
    import httpx
    msg = str(exc).upper()
    retryable_codes = {"SYSTEM_ERROR", "BIZERR_NEED_RETRY", "FREQUENCY_LIMITED"}
    if any(code in msg for code in retryable_codes):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    return False


async def _update_order_after_refund(session, order_id: int, status: str, refund_id: str = None):
    result = await session.execute(
        select(BookingOrder).where(BookingOrder.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        return

    if order.business_type == "tournament":
        order.refund_status = status
        if status == "success":
            order.status = OrderStatus.refunded
            order.refund_time = datetime.utcnow()
        return

    if status == "success":
        order.status = OrderStatus.refunded
        slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
        slots_result = await session.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
        )
        slots = slots_result.scalars().all()

        # Find other active bookings sharing any of these slots
        other_active_result = await session.execute(
            select(BookingOrder).where(
                BookingOrder.id != order.id,
                BookingOrder.status.in_([OrderStatus.pending, OrderStatus.paid, OrderStatus.refunding]),
            )
        )
        other_active_ids = set()
        for other in other_active_result.scalars().all():
            other_slots = other.slot_ids or ([other.slot_id] if other.slot_id else [])
            other_active_ids.update(other_slots)

        for slot in slots:
            should_release = False
            if _v(slot.status) == "locked" and slot.locked_by == order.user_id:
                should_release = True
            elif _v(slot.status) == "booked":
                if slot.id not in other_active_ids:
                    should_release = True
            if should_release:
                slot.status = SlotStatus.available
                slot.locked_by = None
                slot.locked_at = None
                lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
                await release_lock(lock_key, str(order.user_id))
    elif status in ("closed", "abnormal", "failed"):
        order.status = OrderStatus.paid
        order.refund_status = status


async def _retry_failed_refunds_impl():
    """Retry failed or pending refund submissions to WeChat Pay."""
    from app.core.wechat_pay import get_wxpay

    settings = get_settings()
    async with (task_session_factory.get() or async_session_factory)() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(RefundRecord)
            .where(
                RefundRecord.status.in_(["pending", "failed"]),
                RefundRecord.order_id.in_(select(BookingOrder.id).where(BookingOrder.business_type != "tournament")),
                RefundRecord.scheduled_at <= now,
                RefundRecord.retry_count < settings.REFUND_MAX_RETRIES,
            )
            .order_by(RefundRecord.scheduled_at)
            .limit(settings.REFUND_BATCH_SIZE)
        )
        records = result.scalars().all()

        processed = 0
        errors = 0
        wxpay = get_wxpay()

        for rec in records:
            try:
                # First, query current status from WeChat
                query_result = wxpay.query_refund(out_refund_no=rec.out_refund_no)
                refund_state = query_result.get("status", "").upper() if query_result else ""

                if refund_state in ("SUCCESS", "CLOSED", "ABNORMAL"):
                    rec.status = refund_state.lower()
                    rec.wx_refund_id = query_result.get("refund_id", rec.wx_refund_id)
                    rec.completed_at = now
                    await _update_order_after_refund(session, rec.order_id, rec.status, rec.wx_refund_id)
                    await session.commit()
                    processed += 1
                    continue
                elif refund_state == "PROCESSING":
                    rec.status = "processing"
                    await session.commit()
                    processed += 1
                    continue

                # Not in a terminal state: resubmit refund
                # Load order to get transaction id
                order_result = await session.execute(
                    select(BookingOrder).where(BookingOrder.id == rec.order_id)
                )
                order = order_result.scalar_one_or_none()
                tx_id = order.wx_transaction_id if order else None
                resp = wxpay.refund(
                    out_refund_no=rec.out_refund_no,
                    transaction_id=tx_id,
                    out_trade_no=order.order_no if order and not tx_id else None,
                    amount={"refund": _to_cents(rec.amount), "total": _to_cents(order.amount) if order else _to_cents(rec.amount), "currency": "CNY"},
                    reason=rec.reason or "退款重试",
                )
                # Handle the response state properly; only set to processing if WeChat says PROCESSING
                refund_state = (resp.get("status") or "").upper() if resp else ""
                if refund_state in ("SUCCESS", "CLOSED", "ABNORMAL"):
                    rec.status = refund_state.lower()
                    rec.wx_refund_id = resp.get("refund_id", rec.wx_refund_id)
                    rec.completed_at = now
                    await _update_order_after_refund(session, rec.order_id, rec.status, rec.wx_refund_id)
                elif refund_state == "PROCESSING":
                    rec.status = "processing"
                    rec.retry_count += 1
                else:
                    # Unknown state; treat as failed to avoid spinning
                    rec.status = "failed"
                    rec.fail_reason = f"Unexpected refund status from resubmit: {refund_state}"
                    await _update_order_after_refund(session, rec.order_id, "failed")
                await session.commit()
                processed += 1
            except Exception as exc:
                if _is_refund_retryable(exc) and rec.retry_count < settings.REFUND_MAX_RETRIES - 1:
                    rec.retry_count += 1
                    rec.scheduled_at = now + timedelta(seconds=_refund_backoff_seconds(rec.retry_count))
                    rec.fail_reason = str(exc)[:512]
                    await session.commit()
                else:
                    # Non-retryable or max retries reached: mark failed and revert order
                    rec.status = "failed"
                    rec.fail_reason = str(exc)[:512]
                    await _update_order_after_refund(session, rec.order_id, "failed")
                    await session.commit()
                logger.exception("Refund retry failed for record %s", rec.id)
                errors += 1

        return {"processed": processed, "errors": errors}


@celery_app.task(name="app.tasks.tasks.retry_failed_refunds")
def retry_failed_refunds():
    return run_async_task(_retry_failed_refunds_impl)


async def _poll_processing_refunds_impl():
    """Poll WeChat for refunds stuck in PROCESSING status."""
    from app.core.wechat_pay import get_wxpay

    async with (task_session_factory.get() or async_session_factory)() as session:
        now = datetime.utcnow()
        one_min_ago = now - timedelta(minutes=1)
        result = await session.execute(
            select(RefundRecord)
            .where(
                RefundRecord.status == "processing",
                RefundRecord.order_id.in_(select(BookingOrder.id).where(BookingOrder.business_type != "tournament")),
                RefundRecord.updated_at <= one_min_ago,
            )
            .limit(100)
        )
        records = result.scalars().all()

        processed = 0
        errors = 0
        wxpay = get_wxpay()

        for rec in records:
            try:
                query_result = wxpay.query_refund(out_refund_no=rec.out_refund_no)
                refund_state = query_result.get("status", "").upper() if query_result else ""

                if refund_state in ("SUCCESS", "CLOSED", "ABNORMAL"):
                    rec.status = refund_state.lower()
                    rec.wx_refund_id = query_result.get("refund_id", rec.wx_refund_id)
                    rec.completed_at = now
                    await _update_order_after_refund(session, rec.order_id, rec.status, rec.wx_refund_id)
                elif refund_state == "PROCESSING":
                    rec.status = "processing"
                else:
                    rec.status = "failed"
                    rec.fail_reason = f"Unknown refund status: {refund_state}"
                    await _update_order_after_refund(session, rec.order_id, "failed")
                await session.commit()
                processed += 1
            except Exception:
                logger.exception("Poll failed for refund record %s", rec.id)
                await session.rollback()
                errors += 1

        return {"processed": processed, "errors": errors}


@celery_app.task(name="app.tasks.tasks.poll_processing_refunds")
def poll_processing_refunds():
    return run_async_task(_poll_processing_refunds_impl)


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
