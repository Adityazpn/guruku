from fastapi import FastAPI

from app.core.config import get_settings

app = FastAPI(title="AI Education Platform API", version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().app_env}
