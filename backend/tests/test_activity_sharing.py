import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.api.v1 import sharing


@pytest.mark.asyncio
@pytest.mark.parametrize("asset,body", [("code", b'\x89PNG\r\n\x1a\nimage'), ("link", b'{"url_link":"https://wxaurl.cn/test"}')])
async def test_wechat_asset_targets_activity_and_preserves_binary(asset, body):
    async def handler(request):
        import json
        payload = json.loads(request.content)
        assert request.url.params["access_token"] == "private-token"
        if asset == "code":
            assert payload == dict(scene="42", page="pages/common/post-detail", env_version="release",check_path=True,width=430)
        else:
            assert payload["query"] == "id=42"
            assert payload["expire_interval"] == 30
        return httpx.Response(200, content=body)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with patch.object(sharing, "get_wx_access_token", AsyncMock(return_value="private-token")), patch.object(sharing.httpx, "AsyncClient", return_value=client):
        result = await sharing.wechat_asset("post", 42, asset)
    if asset == "code": assert base64.b64decode(result["image_base64"]) == body
    else: assert result["url"] == "https://wxaurl.cn/test"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b'{"errcode":41030,"errmsg":"invalid page"}', b'not-an-image'])
async def test_upstream_failure_never_becomes_fake_code_or_link(body):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=body)))
    with patch.object(sharing,"get_wx_access_token",AsyncMock(return_value="token")), patch.object(sharing.httpx,"AsyncClient",return_value=client):
        with pytest.raises(HTTPException) as exc: await sharing.wechat_asset("tournament",42,"code")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_existing_activity_cache_lock_and_missing_activity():
    db=AsyncMock(); db.get.return_value=SimpleNamespace(status="open")
    cache=AsyncMock(); cache.get.return_value=None; cache.set.return_value=True
    req=Request({"type":"http","client":("127.0.0.1",123)})
    with patch.object(sharing,"get_redis_client",return_value=cache), patch.object(sharing,"check_rate_limit",AsyncMock()), patch.object(sharing,"wechat_asset",AsyncMock(return_value={"url":"https://wxaurl.cn/test"})) as generate:
        assert await sharing.share_asset("post",42,"link",req,db) == {"url":"https://wxaurl.cn/test"}
        cache.setex.assert_awaited_once();cache.delete.assert_awaited_once()
        cache.get.return_value='{"url":"https://wxaurl.cn/cached"}'
        assert (await sharing.share_asset("post",42,"link",req,db))["url"].endswith("cached")
        assert generate.await_count == 1
        db.get.return_value=None
        with pytest.raises(HTTPException) as exc: await sharing.share_asset("post",42,"link",req,db)
        assert exc.value.status_code == 404
        db.get.return_value=SimpleNamespace(status="draft")
        with pytest.raises(HTTPException) as exc: await sharing.share_asset("tournament",42,"code",req,db)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_generation_failure_releases_lock_without_caching():
    db=AsyncMock();db.get.return_value=SimpleNamespace(status="open")
    cache=AsyncMock();cache.get.return_value=None;cache.set.return_value=True
    req=Request({"type":"http","client":("127.0.0.1",123)})
    with patch.object(sharing,"get_redis_client",return_value=cache),patch.object(sharing,"check_rate_limit",AsyncMock()),patch.object(sharing,"wechat_asset",AsyncMock(side_effect=HTTPException(502,"failed"))):
        with pytest.raises(HTTPException):await sharing.share_asset("post",42,"code",req,db)
        cache.delete.assert_awaited_once();cache.setex.assert_not_awaited()
