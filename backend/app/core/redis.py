import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def acquire_lock(key: str, value: str, ttl: int) -> bool:
    """Acquire a distributed lock. Returns True if acquired."""
    return await redis_client.set(key, value, nx=True, ex=ttl)


async def release_lock(key: str) -> None:
    await redis_client.delete(key)


async def get_lock_ttl(key: str) -> int:
    return await redis_client.ttl(key)
