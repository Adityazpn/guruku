"""Credit pricing (pure functions, no DB). Rules come from the admin-editable credit_pricing_rules table.

dynamic: credits = clamp(ceil_step(((api_cost_idr + processing_fee_idr) * (1 + margin_pct/100)) / credit_value_idr))
hybrid : credits = clamp(base_credits + dynamic_variable)
fixed  : credits = fixed_credits
"""
import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class PricingRule:
    mode: str = "fixed"  # fixed | dynamic | hybrid
    fixed_credits: Decimal = Decimal("1")
    base_credits: Decimal = Decimal("0")
    margin_pct: Decimal = Decimal("300")
    processing_fee_idr: Decimal = Decimal("0")
    credit_value_idr: Decimal = Decimal("250")
    rounding_step: Decimal = Decimal("0.5")
    min_credits: Decimal = Decimal("1")
    max_credits: Decimal = Decimal("20")
    reserve_safety_factor: Decimal = Decimal("1.3")

    @property
    def needs_api_cost(self) -> bool:
        return self.mode in ("dynamic", "hybrid")


def ceil_step(x: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return x.quantize(CENT)
    return ((x / step).to_integral_value(rounding=ROUND_CEILING) * step).quantize(CENT)


def _variable(rule: PricingRule, api_cost_idr: Decimal) -> Decimal:
    raw = (api_cost_idr + rule.processing_fee_idr) * (1 + rule.margin_pct / 100) / rule.credit_value_idr
    return ceil_step(raw, rule.rounding_step)


def charge(rule: PricingRule, api_cost_idr: Decimal | None) -> Decimal:
    if rule.mode == "fixed":
        credits = rule.fixed_credits
    else:
        if api_cost_idr is None:
            raise ValueError("api cost required for dynamic/hybrid pricing")
        credits = _variable(rule, api_cost_idr)
        if rule.mode == "hybrid":
            credits += rule.base_credits
    return min(max(credits, rule.min_credits), rule.max_credits).quantize(CENT)


def reserve_amount(rule: PricingRule, estimated_cost_idr: Decimal | None) -> Decimal:
    """What is held before the AI call. Never above max_credits, which is also the most a user can be charged."""
    if rule.mode == "fixed":
        return charge(rule, None)
    est = charge(rule, estimated_cost_idr)
    return min(ceil_step(est * rule.reserve_safety_factor, rule.rounding_step), rule.max_credits).quantize(CENT)


def estimate_range(rule: PricingRule, estimated_cost_idr: Decimal | None) -> tuple[Decimal, Decimal, Decimal]:
    """(expected, min, max) shown to the user before generating."""
    if rule.mode == "fixed":
        c = charge(rule, None)
        return c, c, c
    return charge(rule, estimated_cost_idr), rule.min_credits, reserve_amount(rule, estimated_cost_idr)


__all__ = ["PricingRule", "charge", "reserve_amount", "estimate_range", "ceil_step", "math"]
