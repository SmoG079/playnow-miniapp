"""City weather via Tencent; keys and provider URLs never reach the client."""
from collections import OrderedDict
import math
import re
from time import monotonic

import httpx
from fastapi import HTTPException

from app.core.logger import get_logger
from app.services.tencent_map import service_params

WEATHER_PATH = "/ws/weather/v1/"
WEATHER_URL = "https://apis.map.qq.com" + WEATHER_PATH
logger = get_logger(__name__)
_cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()


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


async def city_weather(city: str, province: str, key: str, secret: str = "", *,
                       adcode: str | None = None, latitude: float | None = None, longitude: float | None = None) -> dict:
    if adcode is not None and not re.fullmatch(r"[1-9]\d{5}", adcode):
        raise HTTPException(422, "无效的行政区划编码")
    if (latitude is None) != (longitude is None):
        raise HTTPException(422, "天气坐标必须同时提供经纬度")
    if latitude is not None:
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise HTTPException(422, "天气坐标无效")
        selector = {"location": f"{latitude},{longitude}"}
    elif adcode:
        selector = {"adcode": adcode}
    else:
        raise HTTPException(422, "请重新选择城市或定位以获取天气位置")
    signature = (province, city, *selector.items())
    cached = _cache.get(signature)
    if cached and cached[0] > monotonic():
        _cache.move_to_end(signature)
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                WEATHER_URL, params=service_params(WEATHER_PATH, {**selector, "type": "now"}, key, secret),
                headers={"x-legacy-url-decode": "no"})
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("status") != 0:
                # Log the provider code only; URLs/messages may contain credentials.
                logger.error("City weather provider rejected request: status=%s", data.get("status"))
            weather = parse_weather(data, city)
    except httpx.HTTPError as exc:
        logger.error("City weather request failed: type=%s", type(exc).__name__)
        raise HTTPException(502, "天气暂不可用") from None
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        logger.error("City weather response validation failed")
        raise HTTPException(502, "天气暂不可用") from None
    _cache[signature] = (monotonic() + 600, weather)
    _cache.move_to_end(signature)
    while len(_cache) > 256:
        _cache.popitem(last=False)
    return weather
