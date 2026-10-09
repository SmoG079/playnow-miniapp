"""Order ownership is persisted on each slot and compared before any release."""

from sqlalchemy import select
from app.models.models import BookingSlot, VenueTimeSlot, SlotStatus
from app.core.redis import release_lock


def lock_owner(order_no):
    return f"booking:{order_no}"


async def locked_order_slots(db, order):
    ids = (
        (
            await db.execute(
                select(BookingSlot.slot_id).where(BookingSlot.order_id == order.id)
            )
        )
        .scalars()
        .all()
    )
    return (
        (
            await db.execute(
                select(VenueTimeSlot)
                .where(VenueTimeSlot.id.in_(ids))
                .order_by(VenueTimeSlot.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )


async def release_order_slots(db, order):
    slots = await locked_order_slots(db, order)
    released = []
    for slot in slots:
        if slot.booking_order_id != order.id:
            continue
        if str(getattr(slot.status, "value", slot.status)) not in ("locked", "booked"):
            continue
        await release_lock(
            f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}",
            lock_owner(order.order_no),
        )
        released.append(slot)
        slot.status = SlotStatus.available
        slot.locked_by = slot.locked_at = slot.booking_order_id = None
    return released


async def expire_slot_orders(db, slot_ids=None, venue_ids=None, day=None):
    from datetime import datetime, timedelta
    from app.core.config import get_settings
    from app.models.models import BookingOrder, OrderStatus

    cutoff = datetime.utcnow() - timedelta(
        seconds=get_settings().BOOKING_LOCK_TTL_SECONDS
    )
    candidates = select(VenueTimeSlot.booking_order_id).where(
        VenueTimeSlot.booking_order_id.isnot(None)
    )
    if slot_ids is not None:
        candidates = candidates.where(VenueTimeSlot.id.in_(slot_ids))
    if venue_ids is not None:
        candidates = candidates.where(
            VenueTimeSlot.venue_id.in_(venue_ids), VenueTimeSlot.date == day
        )
    candidate_ids = list(set((await db.execute(candidates)).scalars().all()))
    if not candidate_ids:
        return
    orders = (
        (
            await db.execute(
                select(BookingOrder)
                .where(
                    BookingOrder.id.in_(candidate_ids),
                    BookingOrder.status == OrderStatus.pending,
                    BookingOrder.created_at <= cutoff,
                )
                .order_by(BookingOrder.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    for order in orders:
        await release_order_slots(db, order)
        order.status = OrderStatus.cancelled
        order.cancel_reason = "Payment timeout"
        order.cancel_time = datetime.utcnow()
    await db.flush()
