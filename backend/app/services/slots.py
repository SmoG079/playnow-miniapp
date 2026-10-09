"""Serialize schedule generation on its venue row; preserve existing intervals."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.models.models import Club, Venue, VenueTimeSlot


def validate_booking_date(value):
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if not today <= value <= today + timedelta(days=2):
        raise HTTPException(422, "仅可预订今天起三天内的时段")


def minutes(value, end=False):
    result = value.hour * 60 + value.minute
    return 1440 if end and result == 0 else result


async def ensure_slots(db, venue_id, day, start=None, end=None, price_for=None):
    await db.execute(select(Venue.id).where(Venue.id == venue_id).with_for_update())
    if start is None or end is None:
        club = (
            await db.execute(
                select(Club)
                .join(Venue, Venue.club_id == Club.id)
                .where(Venue.id == venue_id)
            )
        ).scalar_one()
        start = club.opening_time or time(8)
        end = club.closing_time or time(22)
        if isinstance(start, timedelta):
            start = (datetime.min + start).time()
        if isinstance(end, timedelta):
            end = (datetime.min + end).time()
    existing = (
        (
            await db.execute(
                select(VenueTimeSlot)
                .where(VenueTimeSlot.venue_id == venue_id, VenueTimeSlot.date == day)
                .order_by(VenueTimeSlot.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    intervals = [(minutes(s.start_time), minutes(s.end_time, True)) for s in existing]
    first, last = minutes(start), minutes(end, True)
    if start >= end:
        raise HTTPException(422, "营业结束时间须晚于开始时间")
    created = skipped = 0
    for current in range(first, last - 29, 30):
        stop = current + 30
        if any(a < stop and b > current for a, b in intervals):
            skipped += 1
            continue
        start_time = (datetime.combine(day, time()) + timedelta(minutes=current)).time()
        end_time = (datetime.combine(day, time()) + timedelta(minutes=stop)).time()
        db.add(
            VenueTimeSlot(
                venue_id=venue_id,
                date=day,
                start_time=start_time,
                end_time=end_time,
                price_override=price_for(start_time) if price_for else None,
            )
        )
        intervals.append((current, stop))
        created += 1
    await db.flush()
    return created, skipped
