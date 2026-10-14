"""Weather proxy tests use only isolated provider stubs; no database or network."""
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException, Request
from app.services import weather
from app.services.tencent_map import service_params


def payload(city='扬州市', temperature=0):
    return {'status': 0, 'result': {'realtime': [{'city': city, 'infos': {'temperature': temperature, 'weather': '晴'}, 'update_time': '2026-10-09 15:00'}]}}


@pytest.mark.parametrize('value', [0, -3, '25'])
def test_valid_temperature(value):
    assert weather.parse_weather(payload(temperature=value), '扬州市')['temperature'] == float(value)


@pytest.mark.parametrize('data', [payload('南京市'), payload(temperature=None), payload(temperature=''), payload(temperature=True), payload(temperature=float('nan')), payload(temperature=100), {'status': 113}])
def test_invalid_weather(data):
    with pytest.raises(ValueError): weather.parse_weather(data, '扬州市')


@pytest.mark.asyncio
@pytest.mark.parametrize("position,selector", [(dict(latitude=32.4, longitude=119.4), {"location":"32.4,119.4"}), (dict(adcode="321000"), {"adcode":"321000"})])
async def test_weather_uses_existing_position_signing_and_cache(monkeypatch,position,selector):
    weather._cache.clear()
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params, headers):
            calls.append(url)
            assert url == weather.WEATHER_URL
            assert params == service_params(weather.WEATHER_PATH, {**selector, 'type': 'now'}, 'key', 'secret')
            body = payload()
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: body)
    monkeypatch.setattr(weather.httpx, 'AsyncClient', Client)
    result = await weather.city_weather('扬州市', '江苏省', 'key', 'secret', **position)
    assert await weather.city_weather('扬州市', '江苏省', 'key', 'secret', **position) == result
    assert len(calls) == 1 and 'key' not in result and 'sig' not in result
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
    with pytest.raises(HTTPException) as error: await weather.city_weather('故障市', '', 'key', adcode='321000')
    assert error.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize('position', [{}, {'latitude':32.4}, {'longitude':119.4},
    {'latitude':float('nan'),'longitude':119.4}, {'latitude':91,'longitude':119.4},
    {'adcode':'invalid'}, {'adcode':'000000'}])
async def test_missing_or_invalid_position_never_regeocodes(monkeypatch,position):
    def unexpected(*args,**kwargs): raise AssertionError('No provider call allowed')
    monkeypatch.setattr(weather.httpx,'AsyncClient',unexpected)
    with pytest.raises(HTTPException) as error:
        await weather.city_weather('扬州市','江苏省','key',**position)
    assert error.value.status_code == 422


def test_reverse_geocoder_retains_adcode_for_weather():
    from app.api.v1.discovery import parse_city
    result = parse_city({'status':0,'result':{'address_component':{'city':'扬州市','province':'江苏省','district':'广陵区'},
        'ad_info':{'adcode':321002}}})
    assert result['city'] == '扬州市' and result['adcode'] == '321002'
