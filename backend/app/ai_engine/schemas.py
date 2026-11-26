from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ToolOut(BaseModel):
    slug: str
    name: str
    category: str
    description: str


class ToolDetail(ToolOut):
    input_schema: dict


class EstimateOut(BaseModel):
    mode: str
    expected: Decimal
    min: Decimal
    max: Decimal
    balance: Decimal
    sufficient: bool


class RequestOut(BaseModel):
    id: str
    tool_slug: str
    status: str
    output: dict | None
    error_code: str | None
    credits_reserved: Decimal
    credits_charged: Decimal | None
    created_at: datetime
    finished_at: datetime | None
