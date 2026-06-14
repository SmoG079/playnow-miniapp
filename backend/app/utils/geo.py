"""Geographic utilities."""
from math import radians, cos, sin, asin, sqrt


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float | None:
    """Return great-circle distance in km between two points, rounded to 1 decimal.

    Returns None if any coordinate is missing.
    """
    if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
        return None

    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Earth radius in km
    return round(c * r, 1)
