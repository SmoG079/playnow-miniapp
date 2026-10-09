from contextvars import ContextVar
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


task_redis_client = ContextVar("task_redis_client", default=None)

def get_redis_client():
    return task_redis_client.get() or redis_client


async def acquire_lock(key: str, value: str, ttl: int) -> bool:
    """Acquire a distributed lock. Returns True if acquired."""
    return await get_redis_client().set(key, value, nx=True, ex=ttl)


async def release_lock(key: str, value: str | None = None) -> None:
    """Release a distributed lock. If value is provided, only release if we own it."""
    if value:
        # Atomic check-and-delete using Lua script
        lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        await get_redis_client().eval(lua, 1, key, value)
    else:
        await get_redis_client().delete(key)


async def get_lock_ttl(key: str) -> int:
    return await get_redis_client().ttl(key)
