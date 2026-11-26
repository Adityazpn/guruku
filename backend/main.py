from fastapi import APIRouter, FastAPI

import app.models  # noqa: F401
from app.admin.commerce import router as commerce_router
from app.admin.router import router as admin_router
from app.auth.router import me_router
from app.auth.router import router as auth_router
from app.core import observability
from app.core.config import get_settings
from app.credits.router import router as credits_router
from app.documents.router import router as documents_router
from app.payments.router import router as billing_router
from app.tools.router import router as tools_router

observability.setup(get_settings().app_env)
app = FastAPI(title="AI Education Platform API", version="0.1.0")
app.middleware("http")(observability.request_logging)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/") and "cache-control" not in resp.headers:
        resp.headers["Cache-Control"] = "no-store"  # API responses carry personal data
    if get_settings().app_env != "development":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp

api = APIRouter(prefix="/api/v1")


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}  # liveness only: no environment details are disclosed


@api.get("/ready")
def ready():
    """Readiness: can this instance reach its database and (when used) Redis? 503 otherwise, so the load balancer stops sending traffic."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from app.core import db as dbmod

    checks = {}
    try:
        dbmod.get_engine()
        with dbmod._SessionLocal() as s:
            s.execute(text("select 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001
        checks["database"] = False
    if get_settings().queue_mode == "celery":
        try:
            import redis

            redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2).ping()
            checks["redis"] = True
        except Exception:  # noqa: BLE001
            checks["redis"] = False
    ok = all(checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


api.include_router(auth_router)
api.include_router(me_router)
api.include_router(credits_router)
api.include_router(tools_router)
api.include_router(documents_router)
api.include_router(admin_router)
api.include_router(commerce_router)
api.include_router(billing_router)
app.include_router(api)
