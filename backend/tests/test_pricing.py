from decimal import Decimal as D

import pytest

from app.credits.pricing import PricingRule, charge, estimate_range, reserve_amount

IDR = dict(processing_fee_idr=D("20"), credit_value_idr=D("250"), rounding_step=D("0.5"))


def test_fixed():
    r = PricingRule(mode="fixed", fixed_credits=D("3"))
    assert charge(r, None) == D("3.00")
    assert estimate_range(r, None) == (D("3.00"), D("3.00"), D("3.00"))


def test_dynamic_spec_example():  # SPEC_03 §16: Rp313.5 api cost, +20, x4, /250 = 5.336 -> 5.5
    r = PricingRule(mode="dynamic", margin_pct=D("300"), min_credits=D("2"), max_credits=D("20"), **IDR)
    assert charge(r, D("313.5")) == D("5.50")
    assert reserve_amount(r, D("313.5")) == D("7.50")  # 5.5 * 1.3 = 7.15 -> 7.5


def test_hybrid_spec_example():
    r = PricingRule(mode="hybrid", base_credits=D("3"), margin_pct=D("150"), min_credits=D("4"), max_credits=D("15"), **IDR)
    assert charge(r, D("693")) == D("10.50")


def test_clamps_and_rounding():
    r = PricingRule(mode="dynamic", margin_pct=D("300"), min_credits=D("2"), max_credits=D("6"), **IDR)
    assert charge(r, D("0")) == D("2.00")  # floor
    assert charge(r, D("100000")) == D("6.00")  # ceiling: never above the disclosed max
    assert reserve_amount(r, D("100000")) == D("6.00")  # reserve never above max either


def test_dynamic_requires_cost():
    with pytest.raises(ValueError):
        charge(PricingRule(mode="dynamic"), None)
