"""Ordered court pricing rules, shared by quotes, previews and expiry cleanup."""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

TYPES = {"date_range", "daily_time", "time_range", "weekly", "monthly"}


def validate_rules(rules):
    if rules is None:
        return None
    if len(rules) > 100:
        raise ValueError("价格规则最多100条")
    result = []
    for original in rules:
        try:
            rule = dict(original)
            if rule.get("type") not in TYPES:
                raise ValueError()
            price = Decimal(str(rule["price"]))
            if not price.is_finite() or not 0 <= price <= Decimal("99999999.99") or price.as_tuple().exponent < -2:
                raise ValueError()
            start, end = rule.get("start_time"), rule.get("end_time")
            if bool(start) != bool(end):
                raise ValueError()
            if start:
                a, b = time.fromisoformat(start), time.fromisoformat(end)
                if a >= b or any(t.minute % 30 or t.second or t.microsecond for t in (a, b)):
                    raise ValueError()
                rule.update(start_time=a.strftime("%H:%M"), end_time=b.strftime("%H:%M"))
            if rule["type"] in ("daily_time", "time_range") and not start:
                raise ValueError()
            dates = rule.get("start_date"), rule.get("end_date")
            if any(dates):
                if not all(dates) or date.fromisoformat(dates[0]) > date.fromisoformat(dates[1]):
                    raise ValueError()
                rule.update(start_date=date.fromisoformat(dates[0]).isoformat(), end_date=date.fromisoformat(dates[1]).isoformat())
            elif rule["type"] == "date_range":
                raise ValueError()
            weekdays = rule.get("weekdays")
            if weekdays is not None:
                if not weekdays or any(type(v) is not int or not 1 <= v <= 7 for v in weekdays):
                    raise ValueError()
                rule["weekdays"] = sorted(set(weekdays))
            elif rule["type"] == "weekly":
                raise ValueError()
            first, last = rule.get("start_day"), rule.get("end_day")
            if first is not None or last is not None:
                if type(first) is not int or type(last) is not int or not 1 <= first <= last <= 31:
                    raise ValueError()
            elif rule["type"] == "monthly":
                raise ValueError()
            result.append(rule)
        except (ValueError, TypeError, KeyError, ArithmeticError):
            raise ValueError("价格规则需包含有效日期、星期、月日期及30分钟对齐的时段和非负价格") from None
    return result


def matches(rule, day, start):
    if rule.get("type") not in TYPES:
        return False
    if rule.get("start_date") and not rule["start_date"] <= day.isoformat() <= rule["end_date"]:
        return False
    if rule.get("weekdays") and day.isoweekday() not in rule["weekdays"]:
        return False
    if rule.get("start_day") is not None and not rule["start_day"] <= day.day <= rule["end_day"]:
        return False
    value = start.strftime("%H:%M")
    return not rule.get("start_time") or rule["start_time"] <= value < rule["end_time"]


def quote(base, rules, day, start):
    for index, rule in enumerate(rules or []):
        if matches(rule, day, start) and rule.get("price") is not None:
            return Decimal(str(rule["price"])), index
    return Decimal(str(base or 0)), None


def expires_at(rule):
    if not rule.get("end_date"):
        return None
    # Find the last actual match, including optional weekday/month-day filters.
    day = date.fromisoformat(rule["end_date"])
    first = date.fromisoformat(rule["start_date"])
    from datetime import timedelta
    while day >= first:
        if (not rule.get("weekdays") or day.isoweekday() in rule["weekdays"]) and (rule.get("start_day") is None or rule["start_day"] <= day.day <= rule["end_day"]):
            if rule.get("end_time"):
                return datetime.combine(day, time.fromisoformat(rule["end_time"]), ZoneInfo("Asia/Shanghai"))
            return datetime.combine(day + timedelta(days=1), time(), ZoneInfo("Asia/Shanghai"))
        day -= timedelta(days=1)
    return datetime.combine(first, time(), ZoneInfo("Asia/Shanghai"))
