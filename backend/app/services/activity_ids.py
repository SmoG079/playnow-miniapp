"""One database sequence owns all public post and tournament identifiers."""
from sqlalchemy import select
from contextlib import asynccontextmanager
from fastapi import HTTPException
from redis.exceptions import RedisError
from app.core.redis import redis_client
from app.models.models import Activity


@asynccontextmanager
async def allocation_lock():
    # The lock controls concurrent entry; the database sequence and constraints
    # remain authoritative even if a lease expires or a Redis node fails over.
    try:
        async with redis_client.lock("activity:id:allocate", timeout=30,
                                     blocking_timeout=5, thread_local=False):
            yield
    except RedisError as exc:
        raise HTTPException(503, "活动编号服务暂时繁忙，请稍后重试") from exc


async def allocate_activity(db, kind):
    if kind not in ("post", "tournament"):
        raise ValueError("Unknown activity type")
    async with allocation_lock():
        activity = Activity(kind=kind)
        db.add(activity)
        await db.flush()
        if not 0 < activity.id <= 9007199254740991:
            raise RuntimeError("Activity sequence exceeded the client-safe integer range")
    return activity.id


async def resolve_activity_id(db, ident, kind):
    activity = await db.get(Activity, ident)
    if activity and activity.kind == kind:
        return ident
    alias = await db.scalar(select(Activity.id).where(
        Activity.kind == kind, Activity.legacy_id == ident,
    ))
    return alias if alias is not None else ident
