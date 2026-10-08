"""Regression checks for Tencent's sorted, raw UTF-8 SN signing protocol."""
from types import SimpleNamespace
import pytest
from app.services.tencent_map import GEOCODER_URL, geocoder_params


def test_raw_unicode_and_reserved_characters_in_signature():
    fields={"address":"扬州 A&B#1"}
    assert geocoder_params(fields,"test-key","test-secret")["sig"]=="a9f7628fb2ae50bef6b2caa29f5a1aaa"
    assert fields=={"address":"扬州 A&B#1"}
    assert geocoder_params(fields,"test-key")==dict(address=fields['address'],key="test-key")
    assert geocoder_params(dict(location="32.4,119.4",get_poi=0),"key","sk")==geocoder_params(dict(get_poi=0,location="32.4,119.4"),"key","sk")


@pytest.mark.asyncio
async def test_both_proxies_sign_requests_without_returning_credentials(monkeypatch):
    from fastapi import Request
    from app.api.v1 import discovery,clubs
    settings=SimpleNamespace(TENCENT_MAP_KEY="test-key",TENCENT_MAP_SK="test-secret")
    monkeypatch.setattr(discovery,"get_settings",lambda:settings)
    monkeypatch.setattr(clubs,"get_settings",lambda:settings)
    async def no_limit(*args): pass
    monkeypatch.setattr(discovery,"check_rate_limit",no_limit)
    calls=[]
    class Client:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,url,params,headers):
            assert url==GEOCODER_URL and headers=={"x-legacy-url-decode":"no"}
            fields={k:v for k,v in params.items() if k not in ("key","sig")}
            assert params==geocoder_params(fields,"test-key","test-secret")
            calls.append(fields)
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"status":0,"result":{"address_component":{"province":"江苏省","city":"扬州市","district":"广陵区"},"address_components":{"city":"扬州市"},"location":{"lat":32.4,"lng":119.4}}})
    monkeypatch.setattr(discovery.httpx,"AsyncClient",Client)
    result=await discovery.location_city(Request({"type":"http","client":("127.0.0.1",1)}),32.4,119.4)
    forward=await clubs.geocode_address(clubs.GeocodeRequest(address="扬州 A&B#1"),None)
    assert result['city']==forward.city=='扬州市' and len(calls)==2
    assert "sig" not in result and "key" not in result
