from fastapi import HTTPException
from app.core.redis import redis_client

lua_script = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return current
"""


async def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """
    Fixed-window rate limiter using Redis Lua script for atomic INCR + EXPIRE.

    - Atomically increments the counter for ``key`` and sets EXPIRE on first increment.
    - If the counter exceeds ``max_requests``, raises HTTPException(status_code=429).
    """
    count = await redis_client.eval(lua_script, 1, key, str(window_seconds))
    if int(count) > max_requests:
        raise HTTPException(
            status_code=429,
            detail="操作过于频繁，请稍后再试",
            headers={"Retry-After": str(window_seconds)},
        )
