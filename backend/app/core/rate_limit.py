from fastapi import HTTPException
from app.core.redis import redis_client


async def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """
    Fixed-window rate limiter using Redis INCR + EXPIRE.

    - Increments the counter for ``key``.
    - If the counter is 1, sets EXPIRE so the key auto-deletes after ``window_seconds``.
    - If the counter exceeds ``max_requests``, raises HTTPException(status_code=429).
    """
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > max_requests:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
