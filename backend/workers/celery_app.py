from celery import Celery
from backend.config import settings

celery_app = Celery(
    "jobagent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.workers.agent_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Short timeouts so Redis absence is detected immediately
    broker_connection_timeout=2,
    broker_connection_retry=False,
    broker_connection_retry_on_startup=False,
    redis_socket_connect_timeout=2,
    redis_socket_timeout=2,
    # Route phase tasks to dedicated queue
    task_routes={
        "backend.workers.agent_tasks.run_phase_task": {"queue": "agents"},
        "backend.workers.agent_tasks.check_schedules": {"queue": "default"},
    },
    beat_schedule={
        "run-agent-schedules": {
            "task": "backend.workers.agent_tasks.check_schedules",
            "schedule": 3600.0, # Run every hour
        },
    }
)
