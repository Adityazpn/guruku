"""Production-safe: creates any missing AI tools with their initial prompt and a default FIXED credit rule.
Never touches providers, keys or prices, and never overwrites what admins edited.   Usage (from backend/): python ../scripts/seed_tools.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.ai_engine.catalog import seed_all  # noqa: E402
from app.core import db as dbmod  # noqa: E402

dbmod.get_engine()
with dbmod._SessionLocal() as db:
    made = seed_all(db)
    db.commit()
print("created:", made or "nothing (all tools already exist)")
