from fastapi import APIRouter, FastAPI

import app.models  # noqa: F401
from app.admin.router import router as admin_router
from app.auth.router import me_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.credits.router import router as credits_router
from app.tools.router import router as tools_router

app = FastAPI(title="AI Education Platform API", version="0.1.0")

api = APIRouter(prefix="/api/v1")


@api.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env}


api.include_router(auth_router)
api.include_router(me_router)
api.include_router(credits_router)
api.include_router(tools_router)
api.include_router(admin_router)
app.include_router(api)
