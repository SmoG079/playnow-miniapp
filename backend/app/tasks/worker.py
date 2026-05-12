from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "club_miniapp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    beat_schedule={
        "release-expired-locks": {
            "task": "app.tasks.tasks.release_expired_locks",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)

app = celery_app  # Celery CLI looks for 'app' or 'celery'

# Import tasks so they're registered
import app.tasks.tasks  # noqa
