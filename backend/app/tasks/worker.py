from celery import Celery
from celery.schedules import crontab
from app.core.config import get_settings
from app.core.logger import setup_logging

settings = get_settings()
setup_logging(settings)

celery_app = Celery(
    "club_miniapp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    worker_hijack_root_logger=False,
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
        "generate-daily-slots": {
            "task": "app.tasks.tasks.generate_daily_slots",
            "schedule": crontab(hour=2, minute=0),  # 02:00 daily
        },
        "execute-pending-settlements": {
            "task": "app.tasks.tasks.execute_pending_settlements",
            "schedule": crontab(hour=3, minute=0),  # 03:00 daily
        },
        "retry-failed-refunds": {
            "task": "app.tasks.tasks.retry_failed_refunds",
            "schedule": 300.0,
        },
        "poll-processing-refunds": {
            "task": "app.tasks.tasks.poll_processing_refunds",
            "schedule": crontab(minute="*/5"),
        },
        "cleanup-old-slots": {
            "task": "app.tasks.tasks.cleanup_old_slots",
            "schedule": crontab(hour=4, minute=0),  # 04:00 daily
        },
    },
)

app = celery_app  # Celery CLI looks for 'app' or 'celery'

# Import tasks so they're registered
import app.tasks.tasks  # noqa
