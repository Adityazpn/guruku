"""Development seed: the TP tool, a FAKE provider/model and ILLUSTRATIVE prices. Never run against production.
Usage (from backend/):  python ../scripts/seed_dev.py"""
import sys
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.ai_engine.seed import seed_tp_tool  # noqa: E402
from app.ai_providers.models import AiModel, AiModelPricing, AiProvider, AiToolModelAssignment, FxRate  # noqa: E402
from app.core import db as dbmod  # noqa: E402
from app.core.db import utcnow  # noqa: E402
from app.credits.pricing_models import CreditPricingRule  # noqa: E402

dbmod.get_engine()
with dbmod._SessionLocal() as db:
    tool = seed_tp_tool(db)
    if not db.query(AiProvider).filter_by(code="fake").first():
        prov = AiProvider(code="fake", name="Fake (dev only)", status="enabled")
        db.add(prov)
        db.flush()
        m = AiModel(provider_id=prov.id, model_code="fake-model", max_output_tokens=4000)
        db.add(m)
        db.flush()
        db.add_all([
            AiModelPricing(model_id=m.id, input_per_1m=D("1"), output_per_1m=D("4"), effective_from=utcnow() - timedelta(days=1)),
            AiToolModelAssignment(tool_id=tool.id, model_id=m.id, priority=0),
            FxRate(rate=D("16500"), effective_from=utcnow() - timedelta(days=1)),
            CreditPricingRule(tool_slug="tp-generator", mode="fixed", fixed_credits=D("3"), min_credits=D("1"), max_credits=D("20")),
        ])
    db.commit()
print("seeded")
