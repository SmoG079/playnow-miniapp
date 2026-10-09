"""Use the same slot quote for the selection grid and booking orders."""
from decimal import Decimal, ROUND_HALF_UP


def hourly_slot_price(venue, slot) -> Decimal:
    """Keep existing venue-rule precedence and exclusive time-range endings."""
    base = slot.price_override if slot.price_override is not None else venue.price_per_hour
    slot_time = slot.start_time.strftime("%H:%M")
    for rule in getattr(venue, "price_rules", None) or []:
        price = rule.get("price")
        if price is None:
            continue
        rule_type = rule.get("type", "")
        start = rule.get("start_time", "")
        end = rule.get("end_time", "")
        if rule_type == "date_range":
            date_from = rule.get("start_date", "")
            date_to = rule.get("end_date", "")
            if not date_from or not date_to or not date_from <= str(slot.date) <= date_to:
                continue
            if start and slot_time < start:
                continue
            if end and slot_time >= end:
                continue
            return Decimal(str(price))
        if rule_type in ("time_range", "daily_time") and start and end and start <= slot_time < end:
            return Decimal(str(price))
    return Decimal(str(base or 0))


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
