"""NTRP requirements shared by tournament schemas and discovery."""
from decimal import Decimal, InvalidOperation


def normalize_requirement(value):
    if value is None or not value.strip() or value.strip() == "不限":
        return None
    parts=value.strip().replace("–", "-").replace("—", "-").split("-")
    try:
        levels=[Decimal(p.strip()) for p in parts]
        if len(levels) not in (1,2) or any(not n.is_finite() or not 1 <= n <= 7 or n*2 != (n*2).to_integral_value() for n in levels) or levels[0]>levels[-1]:
            raise ValueError()
    except (InvalidOperation,ValueError):
        raise ValueError("NTRP 请填写1.0–7.0的半级值或范围，例如3.0或3.0-4.0") from None
    return "-".join(f"{n:.1f}" for n in levels)
