import os
import subprocess
import sys
import time
from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import update

from app import worker
from app.ai_engine import engine as eng
from app.ai_engine.models import AiRequest
from app.ai_providers.adapters.fake import FakeProvider
from app.core.db import utcnow
from app.credits import service as cs
from tests.aihelpers import TP_INPUT, VALID, make_user, reset_fake, setup_ai


def test_celery_is_configured_for_safe_redelivery_and_schedules_jobs():
    c = worker.celery_app.conf
    assert c.task_acks_late and c.task_reject_on_worker_lost and c.worker_prefetch_multiplier == 1
    tasks = {v["task"] for v in c.beat_schedule.values()}
    assert tasks == {"credits.sweep_reservations", "credits.expire_buckets", "ai.recover_stuck"}


def submit(pg):
    with pg() as db:
        setup_ai(db)
        u, w = make_user(db)
        db.commit()
        uid, wid = u.id, w.id
    with pg() as db:
        rid = eng.submit(db, uid, "tp-generator", TP_INPUT, "worker-key-1").id
    return wid, rid


def age(pg, rid, **cols):
    with pg() as db:
        db.execute(update(AiRequest).where(AiRequest.id == rid).values(**cols))
        db.commit()


def test_recover_redispatches_lost_queued_job(pg):
    wid, rid = submit(pg)
    sent = []
    with pg() as db:
        assert eng.recover_stuck(db, sent.append) == {"redispatched": 0, "failed": 0}  # too fresh
    age(pg, rid, created_at=utcnow() - timedelta(minutes=5))
    with pg() as db:
        assert eng.recover_stuck(db, sent.append)["redispatched"] == 1
    assert sent == [rid]


def test_recover_requeues_crashed_job_once_then_fails_and_refunds(pg):
    wid, rid = submit(pg)
    old = utcnow() - timedelta(minutes=30)
    age(pg, rid, status="running", started_at=old, attempts=1)
    sent = []
    with pg() as db:
        assert eng.recover_stuck(db, sent.append) == {"redispatched": 1, "failed": 0}
        assert db.get(AiRequest, rid).status == "queued"
    age(pg, rid, status="running", started_at=old, attempts=2)  # crashed again
    with pg() as db:
        assert eng.recover_stuck(db, sent.append) == {"redispatched": 0, "failed": 1}
        r = db.get(AiRequest, rid)
        assert (r.status, r.error_code) == ("failed", "worker_lost")
        assert cs.summary(db, wid)["total"] == D("10.00")  # hold returned


def test_beat_tasks_run_against_the_database(pg, monkeypatch):
    wid, rid = submit(pg)
    monkeypatch.setattr("app.core.db._SessionLocal", pg, raising=False)
    monkeypatch.setattr("app.core.db.get_engine", lambda: None)
    assert worker.sweep_reservations() == 0
    assert worker.expire_buckets() == 0
    assert worker.recover_stuck() == {"redispatched": 0, "failed": 0}


@pytest.mark.skipif(not os.environ.get("TEST_REDIS_URL"), reason="TEST_REDIS_URL not set")
def test_real_worker_processes_a_job_via_redis(pg, monkeypatch):
    """Spawns an actual Celery worker process against Redis + PostgreSQL."""
    reset_fake()
    wid, rid = submit(pg)
    env = {**os.environ, "REDIS_URL": os.environ["TEST_REDIS_URL"], "DATABASE_URL": os.environ["TEST_DATABASE_URL"],
           "FAKE_PROVIDER_REPLY": VALID}
    # the worker is a separate process, so it uses the fake provider's default reply; we only need a schema-valid one
    code = ("import json,sys;from app.ai_providers.adapters import fake;"
            "fake.FakeProvider.script=[sys.argv[1]]*5;"
            "from app.worker import celery_app;celery_app.worker_main(['worker','-l','warning','-Q','default','-c','1','-P','solo'])")
    proc = subprocess.Popen([sys.executable, "-c", code, VALID], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(3)
        import redis
        from celery import Celery

        client = Celery(broker=os.environ["TEST_REDIS_URL"])
        client.send_task("ai.process_request", args=[str(rid)], queue="default")
        status = None
        for _ in range(60):
            with pg() as db:
                status = db.get(AiRequest, rid).status
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.5)
        assert status == "succeeded", proc.stdout.read1().decode() if proc.poll() is not None else status
        with pg() as db:
            assert cs.summary(db, wid)["total"] == D("7.00")
        redis.Redis.from_url(os.environ["TEST_REDIS_URL"]).close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert FakeProvider is not None  # (module import kept for the subprocess script above)


def test_worker_process_registers_every_table():
    """Regression: a worker that only imported celery/ai modules crashed with NoReferencedTableError('users')."""
    code = "import app.worker; from app.core.db import Base; Base.metadata.sorted_tables; assert 'users' in Base.metadata.tables"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


def test_error_after_claim_releases_credits_instead_of_stranding_request(pg):
    """Regression: an exception between claim and the model call left the request 'running' with credits held."""
    from app.ai_engine.models import AiPromptVersion

    wid, rid = submit(pg)
    with pg() as db:
        db.query(AiPromptVersion).update({"user_template": "{{ undefined_variable.boom }}"})
        db.commit()
    with pg() as db:
        r = eng.process(db, rid, sleep=lambda s: None)
        assert r.status == "failed" and r.error_code
        assert cs.summary(db, wid)["total"] == D("10.00")
