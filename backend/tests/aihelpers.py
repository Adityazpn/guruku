from datetime import timedelta
from decimal import Decimal as D

from app.ai_engine.seed import seed_tp_tool
from app.ai_providers.adapters.fake import FakeProvider
from app.ai_providers.models import AiModel, AiModelPricing, AiProvider, AiToolModelAssignment, FxRate
from app.core.db import utcnow
from app.credits import service as cs
from app.credits.models import BucketType, TxType
from app.credits.pricing_models import CreditPricingRule
from app.users.models import User

VALID = ('{"tujuan_pembelajaran":[{"tujuan":"Peserta didik mampu menjelaskan pecahan.",'
         '"indikator":["Menyebutkan pengertian pecahan"],"level_kognitif":"C2"}],"catatan":"draf"}')

TP_INPUT = {"education_level": "SD/MI", "curriculum": "Kurikulum Merdeka", "subject": "Matematika",
            "grade": "4", "topic": "Pecahan"}


def reset_fake():
    FakeProvider.script, FakeProvider.calls = [], []


def setup_ai(db, *, mode="dynamic", models=1, credits_amount=10, fx=True, pricing=True, provider_kwargs=None):
    """Seeds tool + fake provider(s)/model(s) with ILLUSTRATIVE prices (1.00 in / 4.00 out per 1M tokens, Rp16.500/USD)."""
    tool = seed_tp_tool(db)
    prov = AiProvider(code="fake", name="Fake", status="enabled", **(provider_kwargs or {}))
    db.add(prov)
    db.flush()
    ms = []
    for i in range(models):
        m = AiModel(provider_id=prov.id, model_code=f"fake-{i}", max_output_tokens=4000)
        db.add(m)
        db.flush()
        if pricing:
            db.add(AiModelPricing(model_id=m.id, input_per_1m=D("1.0"), output_per_1m=D("4.0"),
                                  effective_from=utcnow() - timedelta(days=1)))
        db.add(AiToolModelAssignment(tool_id=tool.id, model_id=m.id, priority=i))
        ms.append(m)
    if fx:
        db.add(FxRate(rate=D("16500"), effective_from=utcnow() - timedelta(days=1)))
    db.add(CreditPricingRule(tool_slug="tp-generator", mode=mode, fixed_credits=D("2"), base_credits=D("0"),
                             margin_pct=D("300"), processing_fee_idr=D("20"), credit_value_idr=D("250"),
                             rounding_step=D("0.5"), min_credits=D("1"), max_credits=D("20")))
    db.flush()
    return tool, prov, ms


def make_user(db, email="u@example.com", credits_amount=10):
    u = User(email=email, password_hash="x")
    db.add(u)
    db.flush()
    w = cs.get_or_create_wallet(db, u.id)
    if credits_amount:
        cs.grant(db, w, bucket_type=BucketType.bonus, amount=credits_amount, source_type="test", source_id=email,
                 tx_type=TxType.bonus)
    db.flush()
    return u, w
