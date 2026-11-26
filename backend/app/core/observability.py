"""Structured JSON logs with a request id, optional Sentry. Never logs bodies, headers, query strings or secrets."""
import contextvars
import json
import logging
import os
import time
import uuid

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname, "logger": record.name,
               "msg": record.getMessage(), "request_id": request_id_var.get()}
        for k in ("method", "path", "status", "ms"):
            if hasattr(record, k):
                out[k] = getattr(record, k)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def setup(app_env: str) -> None:
    if app_env == "development":
        logging.basicConfig(level=logging.INFO)
    else:
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        root = logging.getLogger()
        root.handlers[:] = [h]
        root.setLevel(logging.INFO)
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0.0, environment=app_env)


log = logging.getLogger("access")


async def request_logging(request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    t0 = time.monotonic()
    try:
        resp = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        raise
    finally:
        request_id_var.reset(token)
    resp.headers["X-Request-ID"] = rid
    log.info("request", extra={"method": request.method, "path": request.url.path, "status": resp.status_code, "ms": int((time.monotonic() - t0) * 1000)})
    return resp
