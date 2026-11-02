import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.main import health

@pytest.mark.asyncio
@pytest.mark.parametrize('mysql_ok,redis_ok', [(True,True),(False,True),(True,False),(False,False)])
async def test_readiness_probes_both_dependencies(mysql_ok, redis_ok):
    execute = AsyncMock(side_effect=None if mysql_ok else RuntimeError('private connection details'))
    @asynccontextmanager
    async def connect():
        yield SimpleNamespace(execute=execute)
    ping = AsyncMock(side_effect=None if redis_ok else RuntimeError('private redis details'))
    with patch('app.main.engine', SimpleNamespace(connect=connect)), patch('app.core.redis.get_redis_client', return_value=SimpleNamespace(ping=ping)):
        response = await health()
    assert response.status_code == (200 if mysql_ok and redis_ok else 503)
    data = json.loads(response.body)
    assert data['mysql'] == ('ok' if mysql_ok else 'unavailable')
    assert data['redis'] == ('ok' if redis_ok else 'unavailable')
    execute.assert_awaited_once()
    ping.assert_awaited_once()
    assert b'private' not in response.body
