from datetime import datetime, timezone
from sqlalchemy import select, update
from app.tasks.worker import celery_app
from app.core.database import async_session_factory, engine
from app.core.redis import release_lock
from app.models.models import VenueTimeSlot, SlotStatus, BookingOrder, OrderStatus


@celery_app.task(name="release_expired_locks")
def release_expired_locks():
    """Release venue time slots that have been locked but not paid within TTL (10min)."""
    import asyncio

    async def _release():
        async with async_session_factory() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(VenueTimeSlot).where(
                    VenueTimeSlot.status == SlotStatus.locked,
                    VenueTimeSlot.locked_at.isnot(None),
                )
            )
            expired_slots = result.scalars().all()

            for slot in expired_slots:
                if slot.locked_at:
                    elapsed = (now - slot.locked_at).total_seconds()
                    if elapsed >= 600:  # 10 minutes
                        slot.status = SlotStatus.available
                        slot.locked_by = None
                        slot.locked_at = None
                        lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
                        await release_lock(lock_key)

                        # Cancel pending bookings for this slot
                        await session.execute(
                            update(BookingOrder)
                            .where(
                                BookingOrder.slot_id == slot.id,
                                BookingOrder.status == OrderStatus.pending,
                            )
                            .values(status=OrderStatus.cancelled, cancel_reason="Payment timeout")
                        )

            await session.commit()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_release())
    return f"Released {0} expired locks"  # Placeholder
