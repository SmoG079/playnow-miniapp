import logging
from datetime import datetime, timezone, date, time, timedelta
from sqlalchemy import select, update
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
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


async def _release_expired_locks_impl():
    """Release venue time slots that have been locked but not paid within TTL."""
    settings = get_settings()
    released_count = 0
    async with async_session_factory() as session:
        now = datetime.utcnow()  # UTC naive (consistent with DB timestamp convention)
        cutoff = now - timedelta(seconds=settings.BOOKING_LOCK_TTL_SECONDS)
        result = await session.execute(
            select(VenueTimeSlot).where(
                VenueTimeSlot.status == SlotStatus.locked,
                VenueTimeSlot.locked_at.isnot(None),
                VenueTimeSlot.locked_at <= cutoff,
            )
        )
        expired_slots = result.scalars().all()

        for slot in expired_slots:
            lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
            # P0-8: Only release lock if we know who owns it, BEFORE clearing locked_by
            owner_id = slot.locked_by
            if owner_id is not None:
                await release_lock(lock_key, str(owner_id))

            slot.status = SlotStatus.available
            slot.locked_by = None
            slot.locked_at = None

            # Cancel pending bookings for this slot
            await session.execute(
                update(BookingOrder)
                .where(
                    BookingOrder.slot_id == slot.id,
                    BookingOrder.status == OrderStatus.pending,
                )
                .values(status=OrderStatus.cancelled, cancel_reason="Payment timeout")
            )
            released_count += 1

        await session.commit()
        return released_count


@celery_app.task(name="release_expired_locks")
def release_expired_locks():
    released = async_to_sync(_release_expired_locks_impl)()
    return f"Released {released} expired locks"


async def _generate_daily_slots_impl():
    """Generate time slots for all active venues for the next 7 days."""
    async with async_session_factory() as session:
        from app.models.models import Venue, VenueStatus

        result = await session.execute(
            select(Venue).where(Venue.status == VenueStatus.active)
        )
        venues = result.scalars().all()

        created_total = 0
        today = date.today()
        for venue in venues:
            opening = venue.opening_time or time(8, 0)
            closing = venue.closing_time or time(22, 0)
            interval = venue.slot_interval_minutes or 60

            for day_offset in range(7):
                current_date = today + timedelta(days=day_offset)
                slot_start = datetime.combine(current_date, opening)
                slot_end = datetime.combine(current_date, closing)

                while slot_start + timedelta(minutes=interval) <= slot_end:
                    next_time = slot_start + timedelta(minutes=interval)
                    existing = await session.execute(
                        select(VenueTimeSlot).where(
                            VenueTimeSlot.venue_id == venue.id,
                            VenueTimeSlot.date == current_date,
                            VenueTimeSlot.start_time == slot_start.time(),
                        )
                    )
                    if not existing.scalars().first():
                        slot = VenueTimeSlot(
                            venue_id=venue.id,
                            date=current_date,
                            start_time=slot_start.time(),
                            end_time=next_time.time(),
                            status=SlotStatus.available,
                        )
                        session.add(slot)
                        created_total += 1
                    slot_start = next_time

        await session.commit()
        return created_total


@celery_app.task(name="generate_daily_slots")
def generate_daily_slots():
    created = async_to_sync(_generate_daily_slots_impl)()
    return f"Generated {created} slots"


async def _execute_pending_settlements_impl():
    """Poll for due pending settlements and execute profit-sharing."""
    from app.services.settlement import execute_settlement, query_settlement_status

    settings = get_settings()
    async with async_session_factory() as session:
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
    return async_to_sync(_execute_pending_settlements_impl)()


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
        select(BookingOrder, VenueTimeSlot)
        .join(VenueTimeSlot, BookingOrder.slot_id == VenueTimeSlot.id)
        .where(BookingOrder.id == order_id)
    )
    row = result.first()
    if not row:
        return
    order, slot = row
    if status == "success":
        order.status = OrderStatus.refunded
        should_release = False
        if _v(slot.status) == "locked" and slot.locked_by == order.user_id:
            should_release = True
        elif _v(slot.status) == "booked":
            other = await session.execute(
                select(BookingOrder).where(
                    BookingOrder.slot_id == slot.id,
                    BookingOrder.id != order.id,
                    BookingOrder.status.in_([OrderStatus.pending, OrderStatus.paid, OrderStatus.refunding]),
                )
            )
            if not other.scalar_one_or_none():
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
    async with async_session_factory() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(RefundRecord)
            .where(
                RefundRecord.status.in_(["pending", "failed"]),
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
    return async_to_sync(_retry_failed_refunds_impl)()


async def _poll_processing_refunds_impl():
    """Poll WeChat for refunds stuck in PROCESSING status."""
    from app.core.wechat_pay import get_wxpay

    async with async_session_factory() as session:
        now = datetime.utcnow()
        one_min_ago = now - timedelta(minutes=1)
        result = await session.execute(
            select(RefundRecord)
            .where(
                RefundRecord.status == "processing",
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
    return async_to_sync(_poll_processing_refunds_impl)()


async def _process_wx_callback_impl(event_type: str, data: dict):
    """Process WeChat Pay callback asynchronously after immediate acknowledgment."""
    async with async_session_factory() as session:
        try:
            result = await process_callback(event_type, data, session)
            await session.commit()
            return result
        except Exception:
            logger.exception("process_wx_callback failed for event_type=%s", event_type)
            await session.rollback()
            raise


@celery_app.task(name="app.tasks.tasks.process_wx_callback")
def process_wx_callback(event_type: str, data: dict):
    return async_to_sync(_process_wx_callback_impl)(event_type, data)
