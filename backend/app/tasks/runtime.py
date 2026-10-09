"""Each synchronous Celery invocation owns its async resources and event loop."""

from contextvars import ContextVar
from asgiref.sync import async_to_sync
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
import redis.asyncio as aioredis
from app.core.config import get_settings
from app.core.redis import task_redis_client

task_session_factory = ContextVar("task_session_factory", default=None)


def run_async_task(operation, *args, **kwargs):
    async def run():
        settings = get_settings()
        engine = create_async_engine(
            settings.DATABASE_URL, poolclass=NullPool, hide_parameters=True
        )
        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        db_token = task_session_factory.set(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        redis_token = task_redis_client.set(redis)
        try:
            return await operation(*args, **kwargs)
        finally:
            task_session_factory.reset(db_token)
            task_redis_client.reset(redis_token)
            try:
                await redis.aclose()
            finally:
                await engine.dispose()

    return async_to_sync(run)()
