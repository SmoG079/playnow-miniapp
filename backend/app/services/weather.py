"""City weather via Tencent; keys and provider URLs never reach the client."""
from collections import OrderedDict
import math
from time import monotonic

import httpx
from fastapi import HTTPException

from app.core.logger import get_logger
from app.services.tencent_map import GEOCODER_URL, geocoder_params, service_params

WEATHER_PATH = "/ws/weather/v1/"
WEATHER_URL = "https://apis.map.qq.com" + WEATHER_PATH
logger = get_logger(__name__)
_cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()


def parse_weather(data: dict, city: str) -> dict:
    if not isinstance(data, dict) or data.get("status") != 0:
        raise ValueError("Provider rejected weather request")
    realtime = data["result"]["realtime"][0]
    value = realtime["infos"]["temperature"]
    if isinstance(value, bool) or value is None or value == "":
        raise ValueError("Missing temperature")
    temperature = float(value)
    if not math.isfinite(temperature) or not -90 <= temperature <= 65:
        raise ValueError("Invalid temperature")
    # Never label a provider fallback to another city as the selected city's weather.
    provider_city = realtime.get("city") or realtime.get("district")
    if provider_city != city and realtime.get("district") != city:
        raise ValueError("Weather city mismatch")
    return dict(city=city, temperature=temperature,
                condition=realtime["infos"].get("weather", ""),
                observed_at=realtime.get("update_time", ""))


async def city_weather(city: str, province: str, key: str, secret: str = "") -> dict:
    signature = (province, city)
    cached = _cache.get(signature)
    if cached and cached[0] > monotonic():
        _cache.move_to_end(signature)
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            geocode = await client.get(
                GEOCODER_URL, params=geocoder_params({"address": province + city, "region": city}, key, secret),
                headers={"x-legacy-url-decode": "no"})
            geocode.raise_for_status()
            data = geocode.json()
            if data.get("status") != 0:
                raise ValueError("City resolution failed")
            result = data["result"]
            resolved = result.get("address_components") or result.get("address_component") or {}
            if resolved.get("city") != city and resolved.get("district") != city:
                raise ValueError("Resolved city mismatch")
            location = result["location"]
            response = await client.get(
                WEATHER_URL, params=service_params(WEATHER_PATH, {"location": f'{location["lat"]},{location["lng"]}', "type": "now"}, key, secret),
                headers={"x-legacy-url-decode": "no"})
            response.raise_for_status()
            weather = parse_weather(response.json(), city)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        logger.error("City weather provider failed")
        raise HTTPException(502, "天气暂不可用") from None
    _cache[signature] = (monotonic() + 600, weather)
    _cache.move_to_end(signature)
    while len(_cache) > 256:
        _cache.popitem(last=False)
    return weather
