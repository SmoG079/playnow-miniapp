"""Weather proxy tests use only isolated provider stubs; no database or network."""
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException, Request
from app.services import weather
from app.services.tencent_map import geocoder_params, service_params


def payload(city='扬州市', temperature=0):
    return {'status': 0, 'result': {'realtime': [{'city': city, 'infos': {'temperature': temperature, 'weather': '晴'}, 'update_time': '2026-10-09 15:00'}]}}


@pytest.mark.parametrize('value', [0, -3, '25'])
def test_valid_temperature(value):
    assert weather.parse_weather(payload(temperature=value), '扬州市')['temperature'] == float(value)


@pytest.mark.parametrize('data', [payload('南京市'), payload(temperature=None), payload(temperature=''), payload(temperature=True), payload(temperature=float('nan')), payload(temperature=100), {'status': 113}])
def test_invalid_weather(data):
    with pytest.raises(ValueError): weather.parse_weather(data, '扬州市')


@pytest.mark.asyncio
async def test_city_resolution_signing_and_cache(monkeypatch):
    weather._cache.clear()
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params, headers):
            calls.append(url)
            if url == weather.GEOCODER_URL:
                assert params == geocoder_params({'address': '江苏省扬州市', 'region': '扬州市'}, 'key', 'secret')
                body = {'status': 0, 'result': {'location': {'lat': 32.4, 'lng': 119.4}, 'address_components': {'city': '扬州市'}}}
            else:
                assert params == service_params(weather.WEATHER_PATH, {'location': '32.4,119.4', 'type': 'now'}, 'key', 'secret')
                body = payload()
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
    monkeypatch.setattr(weather.httpx, 'AsyncClient', Client)
    result = await weather.city_weather('扬州市', '江苏省', 'key', 'secret')
    assert await weather.city_weather('扬州市', '江苏省', 'key', 'secret') == result
    assert len(calls) == 2 and 'key' not in result and 'sig' not in result
    weather._cache.clear()


@pytest.mark.asyncio
async def test_missing_key_and_provider_failure(monkeypatch):
    from app.api.v1 import discovery
    req = Request({'type': 'http', 'client': ('127.0.0.1', 1)})
    monkeypatch.setattr(discovery, 'get_settings', lambda: SimpleNamespace(TENCENT_MAP_KEY=''))
    with pytest.raises(HTTPException) as error: await discovery.weather(req, '扬州市', '江苏省')
    assert error.value.status_code == 503
    async def failed(*args, **kwargs): raise httpx.ConnectError('isolated failure')
    monkeypatch.setattr(weather.httpx.AsyncClient, 'get', failed)
    with pytest.raises(HTTPException) as error: await weather.city_weather('故障市', '', 'key')
    assert error.value.status_code == 502
