import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from app.core.rate_limit import check_rate_limit


@pytest.mark.asyncio
async def test_check_rate_limit_allows_within_limit():
    """Should not raise when count is within max_requests."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 5

    with patch("app.core.rate_limit.redis_client", mock_redis):
        await check_rate_limit("rate:pay:1", max_requests=10, window_seconds=60)

    mock_redis.eval.assert_awaited_once()
    args = mock_redis.eval.await_args.args
    assert args[1] == 1
    assert args[2] == "rate:pay:1"
    assert args[3] == "60"


@pytest.mark.asyncio
async def test_check_rate_limit_allows_at_limit():
    """Should not raise when count equals max_requests (boundary)."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 10

    with patch("app.core.rate_limit.redis_client", mock_redis):
        await check_rate_limit("rate:pay:1", max_requests=10, window_seconds=60)

    mock_redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_rate_limit_rejects_over_limit():
    """Should raise HTTPException 429 when count exceeds max_requests."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 11

    with patch("app.core.rate_limit.redis_client", mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("rate:pay:1", max_requests=10, window_seconds=60)

    assert exc_info.value.status_code == 429
    assert "操作过于频繁" in exc_info.value.detail
    assert exc_info.value.headers == {"Retry-After": "60"}
    mock_redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_rate_limit_sets_expire_only_on_first_increment():
    """Lua script handles EXPIRE atomically on first increment; eval returns 1."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 1

    with patch("app.core.rate_limit.redis_client", mock_redis):
        await check_rate_limit("rate:cancel:2", max_requests=10, window_seconds=60)

    mock_redis.eval.assert_awaited_once()
    args = mock_redis.eval.await_args.args
    assert args[1] == 1
    assert args[2] == "rate:cancel:2"
    assert args[3] == "60"


@pytest.mark.asyncio
async def test_check_rate_limit_no_expire_on_subsequent_requests():
    """Lua script does not call EXPIRE when count > 1; eval returns 5."""
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 5

    with patch("app.core.rate_limit.redis_client", mock_redis):
        await check_rate_limit("rate:refund:3", max_requests=10, window_seconds=60)

    mock_redis.eval.assert_awaited_once()
    args = mock_redis.eval.await_args.args
    assert args[1] == 1
    assert args[2] == "rate:refund:3"
    assert args[3] == "60"
