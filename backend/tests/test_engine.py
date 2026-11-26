from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.ai_engine import engine as eng
from app.ai_engine.models import AiCostTracking, AiRequest, AiUsage
from app.ai_providers.adapters.fake import FakeProvider
from app.ai_providers.base import LLMResponse, ProviderAuthError, ProviderTimeout, ProviderUnavailable
from app.ai_providers.models import AiProvider, AiProviderCredential
from app.credits import service as cs
from app.credits.models import CreditReservation, CreditTransaction
from tests.aihelpers import TP_INPUT, VALID, make_user, reset_fake, setup_ai


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    reset_fake()
    monkeypatch.setattr(eng, "RETRY_BACKOFF", (0, 0))


def run(pg, *, mode="dynamic", user_credits=10, key="req-key-0001", data=None, **kw):
    with pg() as db:
        setup_ai(db, mode=mode, **kw)
        u, w = make_user(db, credits_amount=user_credits)
        db.commit()
        uid, wid = u.id, w.id
    with pg() as db:
        req = eng.submit(db, uid, "tp-generator", data or TP_INPUT, key)
        rid = req.id
    return uid, wid, rid


def process(pg, rid):
    with pg() as db:
        r = eng.process(db, rid, sleep=lambda s: None)
        return r.status, r.error_code, r.credits_charged


def balance(pg, wid):
    with pg() as db:
        return cs.summary(db, wid)["total"]


def test_success_dynamic_charges_from_real_usage_and_tracks_cost(pg):
    FakeProvider.script = [VALID]  # fake reports 1000 in / 2000 out
    uid, wid, rid = run(pg)
    assert balance(pg, wid) < D("10")  # reservation held
    assert process(pg, rid) == ("succeeded", None, D("3.00"))
    # cost: 1000*1 + 2000*4 per 1M = $0.009 -> Rp148.5; (148.5+20)*4/250 = 2.696 -> 3.0 credits
    assert balance(pg, wid) == D("7.00")
    with pg() as db:
        c = db.scalar(select(AiCostTracking))
        assert c.cost_usd == D("0.009") and c.cost_idr == D("148.5") and c.is_estimate and c.charge_mode == "dynamic"
        u = db.scalar(select(AiUsage))
        assert (u.input_tokens, u.output_tokens) == (1000, 2000)
        r = db.get(AiRequest, rid)
        assert r.output["tujuan_pembelajaran"] and r.prompt_version_id and r.model_id
    # prompt: user data present, fixed system rules present, no secret
    call = FakeProvider.calls[0]
    assert "Pecahan" in call.user and "DRAF" in call.system and call.max_tokens == 2500


def test_fixed_mode_charges_fixed_and_needs_no_price(pg):
    FakeProvider.script = [VALID]
    _, wid, rid = run(pg, mode="fixed", fx=False, pricing=False)
    assert process(pg, rid)[:2] == ("succeeded", None)
    assert balance(pg, wid) == D("8.00")
    with pg() as db:
        assert db.scalar(select(AiCostTracking)).cost_usd is None  # unknown cost is recorded as unknown, not zero


def test_insufficient_credits_is_402_and_nothing_held(pg):
    with pytest.raises(eng.EngineError) as e:
        run(pg, user_credits=1)  # reserve for this tool is more than 1
    assert (e.value.code, e.value.status) == ("insufficient_credits", 402)
    with pg() as db:
        assert db.query(CreditReservation).count() == 0 and db.query(AiRequest).count() == 0


def test_invalid_input_rejected_before_any_hold(pg):
    with pytest.raises(eng.EngineError) as e:
        run(pg, data={**TP_INPUT, "education_level": "Universitas"})
    assert e.value.status == 422
    with pg() as db:
        assert db.query(CreditReservation).count() == 0


def test_submit_is_idempotent_and_process_is_exactly_once(pg):
    FakeProvider.script = [VALID, VALID]
    uid, wid, rid = run(pg)
    with pg() as db:
        again = eng.submit(db, uid, "tp-generator", TP_INPUT, "req-key-0001")
        assert again.id == rid and db.query(CreditReservation).count() == 1
    assert process(pg, rid)[0] == "succeeded"
    assert process(pg, rid)[0] == "succeeded"  # second worker: no-op
    assert len(FakeProvider.calls) == 1 and balance(pg, wid) == D("7.00")


def test_malformed_output_is_repaired_once_and_all_usage_counted(pg):
    FakeProvider.script = ["not json at all", VALID]
    _, wid, rid = run(pg)
    assert process(pg, rid)[0] == "succeeded"
    assert "JSON valid" in FakeProvider.calls[1].user
    with pg() as db:
        u = db.scalar(select(AiUsage))
        assert (u.input_tokens, u.output_tokens) == (2000, 4000)  # both calls cost us money
        assert db.scalar(select(AiCostTracking)).cost_usd == D("0.018")


def test_malformed_twice_fails_refunds_but_keeps_our_cost(pg):
    FakeProvider.script = ["nope", '{"wrong": 1}']
    _, wid, rid = run(pg)
    assert process(pg, rid) == ("failed", "malformed_output", D("0"))
    assert balance(pg, wid) == D("10.00")  # customer pays nothing for a failed generation
    with pg() as db:
        c = db.scalar(select(AiCostTracking))
        assert c.cost_usd == D("0.018") and c.credits_charged == 0 and c.charge_mode == "failed"


def test_truncated_output_is_treated_as_failure(pg):
    cut = LLMResponse(text=VALID, input_tokens=10, output_tokens=10, finish_reason="length")
    FakeProvider.script = [cut, cut]
    _, wid, rid = run(pg)
    assert process(pg, rid)[:2] == ("failed", "malformed_output")
    assert balance(pg, wid) == D("10.00")


def test_timeouts_are_retried_then_succeed(pg):
    FakeProvider.script = [ProviderTimeout("t"), ProviderTimeout("t"), VALID]
    _, wid, rid = run(pg)
    assert process(pg, rid)[0] == "succeeded" and len(FakeProvider.calls) == 3


def test_failover_to_second_model_when_first_rejects_key(pg):
    FakeProvider.script = [ProviderAuthError("bad key"), VALID]
    _, wid, rid = run(pg, models=2)
    assert process(pg, rid)[0] == "succeeded"
    assert [c.model for c in FakeProvider.calls] == ["fake-0", "fake-1"]


def test_all_providers_down_releases_credits(pg):
    FakeProvider.script = [ProviderUnavailable("x")] * 10
    _, wid, rid = run(pg, models=2)
    assert process(pg, rid) == ("failed", "provider_unavailable", D("0"))
    assert balance(pg, wid) == D("10.00")
    with pg() as db:
        assert db.query(CreditReservation).filter_by(status="released").count() == 1


def test_rejected_stored_key_is_marked_invalid(pg, monkeypatch):
    monkeypatch.setenv("PROVIDER_KEY_MASTER", "m")
    from app.core import config, crypto
    config.get_settings.cache_clear()
    FakeProvider.script = [ProviderAuthError("401")] * 3
    uid, wid, rid = run(pg)
    with pg() as db:
        p = db.scalar(select(AiProvider))
        db.add(AiProviderCredential(provider_id=p.id, secret_ciphertext=crypto.encrypt_secret("sk-x"), last4="sk-x"[-4:]))
        db.commit()
    process(pg, rid)
    with pg() as db:
        assert db.scalar(select(AiProviderCredential)).status == "invalid"
    config.get_settings.cache_clear()


def test_provider_spend_limit_skips_provider(pg):
    FakeProvider.script = [VALID, VALID]
    uid, wid, rid = run(pg, provider_kwargs={"daily_spend_limit_usd": D("0.005")})
    assert process(pg, rid)[0] == "succeeded"  # $0.009 spent, over the $0.005 daily cap
    with pg() as db:
        r2 = eng.submit(db, uid, "tp-generator", TP_INPUT, "req-key-0002")
        rid2 = r2.id
    assert process(pg, rid2) == ("failed", "spend_limit", D("0"))
    assert len(FakeProvider.calls) == 1  # no money spent after the cap
    assert balance(pg, wid) == D("7.00")


def test_dynamic_without_prices_cannot_be_started(pg):
    with pytest.raises(eng.EngineError) as e:
        run(pg, pricing=False)
    assert e.value.code == "pricing_missing"


def test_failure_never_leaves_a_hold_and_ledger_balances(pg):
    FakeProvider.script = [ProviderUnavailable("x")] * 5
    _, wid, rid = run(pg)
    process(pg, rid)
    with pg() as db:
        assert cs.bucket_balances(db, wid) and sum(cs.bucket_balances(db, wid).values()) == D("10.00")
        types = sorted(t.type for t in db.query(CreditTransaction))
        assert types == ["bonus", "reservation_release", "usage_reservation"]
