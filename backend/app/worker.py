"""Celery application. Run with:
    celery -A app.worker.celery_app worker -l info -Q default
    celery -A app.worker.celery_app beat -l info
"""
import uuid

from celery import Celery

import app.models  # noqa: F401  (register every table in this process)
from app.core import db as dbmod
from app.core.config import get_settings

celery_app = Celery("platform", broker=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,  # a task is only acknowledged after it finishes...
    task_reject_on_worker_lost=True,  # ...so a killed worker's job is redelivered
    worker_prefetch_multiplier=1,  # long AI calls: do not hoard jobs
    task_default_queue="default",
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "sweep-credit-reservations": {"task": "credits.sweep_reservations", "schedule": 60.0},
        "expire-credit-buckets": {"task": "credits.expire_buckets", "schedule": 3600.0},
        "subscription-tick": {"task": "subscriptions.tick", "schedule": 900.0},
        "recover-stuck-ai-requests": {"task": "ai.recover_stuck", "schedule": 120.0},
    },
)


def _session():
    dbmod.get_engine()
    return dbmod._SessionLocal()


@celery_app.task(name="ai.process_request", bind=True, max_retries=0)
def process_request(self, request_id: str) -> str:
    from app.ai_engine import engine

    with _session() as db:
        return engine.process(db, uuid.UUID(request_id)).status


@celery_app.task(name="credits.sweep_reservations")
def sweep_reservations() -> int:
    from app.credits import service

    with _session() as db:
        n = service.sweep_expired_reservations(db)
        db.commit()
        return n


@celery_app.task(name="credits.expire_buckets")
def expire_buckets() -> int:
    from app.credits import service

    with _session() as db:
        n = service.expire_buckets(db)
        db.commit()
        return n


@celery_app.task(name="ai.recover_stuck")
def recover_stuck() -> dict:
    from app.ai_engine import engine

    with _session() as db:
        return engine.recover_stuck(db, lambda rid: process_request.delay(str(rid)))


@celery_app.task(name="subscriptions.tick")
def subscription_tick() -> dict:
    from app.subscriptions import service

    with _session() as db:
        return service.tick(db)
