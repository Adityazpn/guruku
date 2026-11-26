from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SummaryOut(BaseModel):
    subscription: Decimal
    bonus: Decimal
    purchased: Decimal
    total: Decimal
    next_expiry: datetime | None


class LedgerRow(BaseModel):
    id: str
    type: str
    amount: Decimal
    description: str
    created_at: datetime
    expires_at: datetime | None


class LedgerPage(BaseModel):
    items: list[LedgerRow]
    page: int
    page_size: int
    total: int
