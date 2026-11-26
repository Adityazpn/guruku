"""How a queued request reaches a worker. Interim: an in-process background task. Replaced by Celery
(same `dispatch(request_id)` contract) when the worker service lands. Tests replace `dispatch` to run inline."""
import uuid

from app.core import db as dbmod


def _run(request_id: uuid.UUID) -> None:
    from app.ai_engine import engine

    dbmod.get_engine()
    with dbmod._SessionLocal() as db:
        engine.process(db, request_id)


def dispatch(request_id: uuid.UUID, background_tasks) -> None:
    background_tasks.add_task(_run, request_id)
