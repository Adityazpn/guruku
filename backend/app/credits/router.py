from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.credits import service
from app.credits.models import CreditTransaction
from app.credits.schemas import LedgerPage, LedgerRow, SummaryOut
from app.users.models import User

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/summary", response_model=SummaryOut)
def get_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = service.get_or_create_wallet(db, user.id)
    db.commit()
    return service.summary(db, wallet.id)


@router.get("/ledger", response_model=LedgerPage)
def get_ledger(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = service.get_or_create_wallet(db, user.id)
    db.commit()
    q = select(CreditTransaction).where(CreditTransaction.wallet_id == wallet.id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(CreditTransaction.created_at.desc(), CreditTransaction.id)
                      .offset((page - 1) * page_size).limit(page_size))
    return LedgerPage(
        items=[LedgerRow(id=str(t.id), type=t.type, amount=t.amount, description=t.description,
                         created_at=t.created_at, expires_at=t.expires_at) for t in rows],
        page=page, page_size=page_size, total=total or 0)
