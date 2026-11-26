"""Creates EXAMPLE plans and credit packages if none exist. Names/credits follow the spec's examples; prices and package prices are
PLACEHOLDERS (marked in the description) and must be reviewed in Admin before launch. Usage (from backend/): python ../scripts/seed_commerce.py"""
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.core import db as dbmod  # noqa: E402
from app.subscriptions.models import CreditPackage, Plan, PlanPrice  # noqa: E402

EX = " (CONTOH, harga belum final)"
PLANS = [("starter", "Starter", 100, 49000, 490000, ["Alat AI dasar", "Pustaka dasar", "Penyimpanan terbatas"]),
         ("professional", "Professional", 300, 99000, 990000, ["Lebih banyak alat AI", "Pustaka premium", "Unduh DOCX & PDF", "Riwayat dokumen"]),
         ("ultimate", "Ultimate", 600, 149000, 1490000, ["Semua alat AI", "Pustaka lengkap", "Semua format dokumen", "AI lanjutan", "Prioritas pemrosesan"])]
PACKAGES = [("100 Kredit", 100, 35000, 0), ("300 Kredit", 300, 99000, 10), ("500 Kredit", 500, 160000, 25), ("1.000 Kredit", 1000, 300000, 75)]

dbmod.get_engine()
with dbmod._SessionLocal() as db:
    if db.query(Plan).count() == 0:
        for i, (code, name, cr, m, a, feats) in enumerate(PLANS):
            p = Plan(code=code, name=name, description=f"{cr} kredit AI per bulan{EX}", credits_monthly=D(cr), features=feats, sort=i)
            db.add(p)
            db.flush()
            db.add_all([PlanPrice(plan_id=p.id, cycle="monthly", amount_idr=m), PlanPrice(plan_id=p.id, cycle="annual", amount_idr=a)])
        print("plans created")
    if db.query(CreditPackage).count() == 0:
        for i, (n, cr, price, bonus) in enumerate(PACKAGES):
            db.add(CreditPackage(name=n, credits=D(cr), price_idr=price, bonus_credits=D(bonus), bonus_expiry_days=30, purchased_expiry_days=365, sort=i))
        print("packages created (placeholder prices)")
    db.commit()
print("Review all prices in the admin panel before opening to customers.")
