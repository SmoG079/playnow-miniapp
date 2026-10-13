"""Use the same slot quote for the selection grid and booking orders."""
from decimal import Decimal, ROUND_HALF_UP


def hourly_slot_price(venue, slot) -> Decimal:
    from app.services.price_rules import quote
    return quote(venue.price_per_hour, getattr(venue, "price_rules", None), slot.date, slot.start_time)[0]


def slot_charge(venue, slot) -> Decimal:
    duration = (slot.end_time.hour * 60 + slot.end_time.minute) - (
        slot.start_time.hour * 60 + slot.start_time.minute
    )
    if duration <= 0 and slot.end_time.hour == 0 and slot.end_time.minute == 0:
        duration += 1440
    price = hourly_slot_price(venue, slot)
    if not price.is_finite() or price < 0 or duration <= 0:
        from fastapi import HTTPException
        raise HTTPException(422, "场地价格或时段无效，请联系管理员修正")
    return (price * Decimal(duration) / Decimal("60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
