"""How a queued request reaches a worker.
QUEUE_MODE=celery      -> Celery task (production).
QUEUE_MODE=background  -> in-process FastAPI background task (local development without Redis only).
If the broker is down the request simply stays `queued`; the `ai.recover_stuck` beat job re-dispatches it."""
import logging
import uuid

from app.core import db as dbmod
from app.core.config import get_settings

log = logging.getLogger(__name__)


def _run(request_id: uuid.UUID) -> None:
    from app.ai_engine import engine

    dbmod.get_engine()
    with dbmod._SessionLocal() as db:
        engine.process(db, request_id)


def dispatch(request_id: uuid.UUID, background_tasks) -> None:
    if get_settings().queue_mode == "celery":
        from app.worker import process_request

        try:
            process_request.delay(str(request_id))
        except Exception:  # noqa: BLE001  broker outage must not fail the user's request
            log.exception("could not enqueue %s; recover_stuck will retry", request_id)
        return
    background_tasks.add_task(_run, request_id)
