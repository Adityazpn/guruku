from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

D = Decimal


class ProviderIn(BaseModel):
    code: str = Field(pattern="^[a-z][a-z0-9_]{1,29}$")
    name: str = Field(min_length=2, max_length=100)
    base_url: str | None = Field(default=None, max_length=300)


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    status: str | None = Field(default=None, pattern="^(enabled|disabled)$")
    base_url: str | None = Field(default=None, max_length=300)
    daily_spend_limit_usd: Decimal | None = Field(default=None, gt=0)
    monthly_spend_limit_usd: Decimal | None = Field(default=None, gt=0)
    clear_limits: bool = False


class CredentialIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)
    label: str = Field(default="", max_length=100)


class ModelIn(BaseModel):
    model_code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(default="", max_length=100)
    max_output_tokens: int = Field(default=4096, ge=256, le=200000)


class ModelPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    max_output_tokens: int | None = Field(default=None, ge=256, le=200000)


class PricingIn(BaseModel):
    input_per_1m: Decimal = Field(ge=0, le=100000)
    output_per_1m: Decimal = Field(ge=0, le=100000)
    cached_input_per_1m: Decimal | None = Field(default=None, ge=0, le=100000)
    effective_from: datetime | None = None


class FxIn(BaseModel):
    rate: Decimal = Field(gt=1000, lt=100000)  # IDR per USD; sanity bounds catch typos like 16.5 or 165000000
    effective_from: datetime | None = None


class TestIn(BaseModel):
    model_id: str


class AssignIn(BaseModel):
    model_ids: list[str] = Field(max_length=10)  # in priority order; later ones are fallbacks


class ToolPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    requires_subscription: bool | None = None
    est_input_tokens: int | None = Field(default=None, ge=1, le=200000)
    est_output_tokens: int | None = Field(default=None, ge=1, le=200000)
    max_output_tokens: int | None = Field(default=None, ge=256, le=200000)


class PromptIn(BaseModel):
    system_prompt: str = Field(min_length=10, max_length=20000)
    user_template: str = Field(min_length=10, max_length=20000)
    temperature: Decimal = Field(default=D("0.3"), ge=0, le=1)
    change_note: str = Field(default="", max_length=300)


class RollbackIn(BaseModel):
    version: int = Field(ge=1)


class PricingRuleIn(BaseModel):
    mode: str = Field(pattern="^(fixed|dynamic|hybrid)$")
    fixed_credits: Decimal = Field(default=D("1"), ge=0, le=1000)
    base_credits: Decimal = Field(default=D("0"), ge=0, le=1000)
    margin_pct: Decimal = Field(default=D("300"), ge=0, le=10000)
    processing_fee_idr: Decimal = Field(default=D("0"), ge=0, le=1000000)
    credit_value_idr: Decimal = Field(default=D("250"), gt=0, le=1000000)
    rounding_step: Decimal = Field(default=D("0.5"), gt=0, le=100)
    min_credits: Decimal = Field(default=D("1"), ge=0, le=1000)
    max_credits: Decimal = Field(default=D("20"), gt=0, le=1000)
    reserve_safety_factor: Decimal = Field(default=D("1.3"), ge=1, le=5)

    @model_validator(mode="after")
    def _bounds(self):
        if self.min_credits > self.max_credits:
            raise ValueError("min_credits must be <= max_credits")
        if self.mode == "fixed" and not (self.min_credits <= self.fixed_credits <= self.max_credits):
            raise ValueError("fixed_credits must be within min/max")
        return self


class GrantIn(BaseModel):
    amount: Decimal = Field(gt=0, le=100000)
    kind: str = Field(default="bonus", pattern="^(bonus|promotional)$")
    expires_in_days: int | None = Field(default=30, ge=1, le=3650)
    reason: str = Field(min_length=3, max_length=300)
