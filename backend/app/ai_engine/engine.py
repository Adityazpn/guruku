"""AI request pipeline: submit (validate -> price -> reserve credits) and process (call model -> validate output
-> record usage & cost -> settle credits, or release on failure). See docs/SPEC_03 §12 and §17."""
import json
import time
import uuid
from decimal import Decimal

import jsonschema
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_engine.models import AiCostTracking, AiPromptVersion, AiRequest, AiTool, AiUsage
from app.ai_providers import costing
from app.ai_providers.base import LLMRequest, MalformedOutput, ProviderAuthError, ProviderError, ProviderQuotaExhausted
from app.ai_providers.models import AiModel, AiProvider, AiToolModelAssignment
from app.ai_providers.registry import build_adapter, resolve_api_key
from app.core.db import utcnow
from app.credits import pricing
from app.credits import service as credits
from app.credits.pricing_models import CreditPricingRule

RETRY_BACKOFF = (0.5, 1.5)  # seconds between retries of a retryable provider error (tests set to zeros)
_jinja = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)


class EngineError(Exception):
    def __init__(self, code: str, status: int = 400, detail: str = ""):
        super().__init__(code)
        self.code, self.status, self.detail = code, status, detail


# ---------- pricing / estimate ----------
def pricing_rule_for(db: Session, slug: str) -> CreditPricingRule | None:
    q = select(CreditPricingRule).where(CreditPricingRule.active.is_(True))
    row = db.scalar(q.where(CreditPricingRule.tool_slug == slug).order_by(CreditPricingRule.version.desc()))
    return row or db.scalar(q.where(CreditPricingRule.tool_slug.is_(None)).order_by(CreditPricingRule.version.desc()))


def _candidates(db: Session, tool: AiTool) -> list[tuple[AiModel, AiProvider]]:
    rows = db.execute(
        select(AiModel, AiProvider).join(AiToolModelAssignment, AiToolModelAssignment.model_id == AiModel.id)
        .join(AiProvider, AiProvider.id == AiModel.provider_id)
        .where(AiToolModelAssignment.tool_id == tool.id, AiModel.status == "active", AiProvider.status == "enabled")
        .order_by(AiToolModelAssignment.priority)
    ).all()
    return [(m, p) for m, p in rows]


def _estimated_cost_idr(db: Session, tool: AiTool, model: AiModel, now) -> Decimal:
    p, fx = costing.get_pricing(db, model.id, now), costing.get_fx(db, now)
    if p is None or fx is None:
        raise EngineError("pricing_missing", 503, "model price or FX rate not configured")
    return costing.cost_usd(p, tool.est_input_tokens, tool.est_output_tokens) * fx.rate


def estimate(db: Session, tool: AiTool) -> dict:
    row = pricing_rule_for(db, tool.slug)
    if row is None:
        raise EngineError("pricing_missing", 503, "no credit pricing rule")
    rule = row.to_rule()
    est_cost = None
    if rule.needs_api_cost:
        cands = _candidates(db, tool)
        if not cands:
            raise EngineError("no_model_available", 503)
        est_cost = _estimated_cost_idr(db, tool, cands[0][0], utcnow())
    expected, lo, hi = pricing.estimate_range(rule, est_cost)
    return {"mode": rule.mode, "expected": expected, "min": lo, "max": hi, "reserve": pricing.reserve_amount(rule, est_cost)}


# ---------- submit ----------
def validate_input(tool: AiTool, data: dict) -> None:
    try:
        jsonschema.validate(data, tool.input_schema)
    except jsonschema.ValidationError as e:
        raise EngineError("invalid_input", 422, e.message) from None


def submit(db: Session, user_id: uuid.UUID, slug: str, data: dict, idempotency_key: str) -> AiRequest:
    tool = db.scalar(select(AiTool).where(AiTool.slug == slug))
    if tool is None or not tool.is_active:
        raise EngineError("tool_not_found", 404)
    existing = db.scalar(select(AiRequest).where(AiRequest.user_id == user_id, AiRequest.idempotency_key == idempotency_key))
    if existing:
        return existing
    validate_input(tool, data)
    est = estimate(db, tool)
    version = db.scalar(select(AiPromptVersion).where(AiPromptVersion.tool_id == tool.id, AiPromptVersion.status == "published")
                        .order_by(AiPromptVersion.version.desc()))
    if version is None:
        raise EngineError("tool_not_ready", 503, "no published prompt")
    wallet = credits.get_or_create_wallet(db, user_id)
    req = AiRequest(user_id=user_id, tool_id=tool.id, prompt_version_id=version.id, status="queued",
                    idempotency_key=idempotency_key, input=data, credits_reserved=est["reserve"])
    db.add(req)
    try:
        db.flush()
    except IntegrityError:  # concurrent twin with the same key
        db.rollback()
        return db.scalar(select(AiRequest).where(AiRequest.user_id == user_id, AiRequest.idempotency_key == idempotency_key))
    try:
        res = credits.reserve(db, wallet.id, est["reserve"], idempotency_key=f"ai:{req.id}", reference_id=str(req.id))
    except credits.InsufficientCredits:
        db.rollback()
        raise EngineError("insufficient_credits", 402) from None
    req.reservation_id = res.id
    db.commit()
    return req


# ---------- process ----------
def _render(version: AiPromptVersion, data: dict) -> str:
    return _jinja.from_string(version.user_template).render(input=data, input_json=json.dumps(data, ensure_ascii=False, indent=2))


def _parse_and_validate(text: str, tool: AiTool) -> dict:
    s = text.strip()
    if s.startswith("```"):  # tolerate fenced JSON
        s = s.strip("`")
        s = s[4:] if s[:4].lower() == "json" else s
    try:
        obj = json.loads(s)
        jsonschema.validate(obj, tool.output_schema)
    except (ValueError, jsonschema.ValidationError) as e:
        raise MalformedOutput(str(e)[:200]) from None
    return obj


def _spend_ok(db: Session, provider: AiProvider, now) -> bool:
    for limit, since in ((provider.daily_spend_limit_usd, now.replace(hour=0, minute=0, second=0, microsecond=0)),
                         (provider.monthly_spend_limit_usd, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))):
        if limit is None:
            continue
        spent = db.scalar(select(func.coalesce(func.sum(AiCostTracking.cost_usd), 0))
                          .join(AiUsage, AiUsage.request_id == AiCostTracking.request_id)
                          .where(AiUsage.provider_id == provider.id, AiCostTracking.created_at >= since))
        if Decimal(spent) >= limit:
            return False
    return True


class _Acc:
    """Usage/cost across every provider call of one request (first call, repair, fallback model)."""

    def __init__(self):
        self.input = self.output = self.cached = 0
        self.usd: Decimal | None = Decimal(0)  # None once any call could not be priced
        self.model: AiModel | None = None
        self.provider: AiProvider | None = None
        self.provider_request_id = ""

    def add(self, db, model, provider, resp, now):
        self.input += resp.input_tokens
        self.output += resp.output_tokens
        self.cached += resp.cached_tokens
        self.model, self.provider, self.provider_request_id = model, provider, resp.provider_request_id
        p = costing.get_pricing(db, model.id, now)
        self.usd = None if (p is None or self.usd is None) else self.usd + costing.cost_usd(
            p, resp.input_tokens, resp.output_tokens, resp.cached_tokens)


def process(db: Session, request_id: uuid.UUID, sleep=time.sleep) -> AiRequest:
    claimed = db.execute(update(AiRequest).where(AiRequest.id == request_id, AiRequest.status == "queued")
                         .values(status="running", started_at=utcnow(), attempts=AiRequest.attempts + 1))
    db.commit()
    req = db.get(AiRequest, request_id)
    if claimed.rowcount != 1:  # someone else owns it, or it already finished
        return req
    tool = db.get(AiTool, req.tool_id)
    version = db.get(AiPromptVersion, req.prompt_version_id)
    acc = _Acc()
    last_err: ProviderError | None = None
    result: dict | None = None
    started = time.monotonic()
    now = utcnow()

    try:
        user_prompt = _render(version, req.input)
        for model, provider in _candidates(db, tool):
            if not _spend_ok(db, provider, now):
                last_err = ProviderError("spend limit reached")
                last_err.code = "spend_limit"
                continue
            key, cred = resolve_api_key(db, provider)
            adapter = build_adapter(provider, key)
            llm_req = LLMRequest(model=model.model_code, system=version.system_prompt, user=user_prompt,
                                 max_tokens=min(tool.max_output_tokens, model.max_output_tokens),
                                 temperature=float(version.temperature))
            repaired = False
            attempt = 0
            while True:
                try:
                    resp = adapter.generate(llm_req)
                    acc.add(db, model, provider, resp, now)
                    if resp.finish_reason == "length":
                        raise MalformedOutput("output truncated (token limit)")
                    result = _parse_and_validate(resp.text, tool)
                    break
                except MalformedOutput as e:
                    last_err = e
                    if repaired:
                        break
                    repaired = True  # one repair attempt: ask again with an explicit reminder
                    llm_req = LLMRequest(model=llm_req.model, system=llm_req.system,
                                         user=user_prompt + "\n\nPENTING: balas HANYA dengan JSON valid sesuai skema; "
                                         "jangan ada teks lain.", max_tokens=llm_req.max_tokens, temperature=0.0)
                except ProviderError as e:
                    last_err = e
                    if cred is not None and isinstance(e, (ProviderAuthError, ProviderQuotaExhausted)):
                        cred.status = "invalid"  # stop using a key the provider rejects; admin is alerted via dashboard
                        db.commit()
                    if e.retryable and attempt < len(RETRY_BACKOFF):
                        sleep(RETRY_BACKOFF[attempt])
                        attempt += 1
                        continue
                    break
            if result is not None:
                break
        if result is None:
            raise last_err or ProviderError("no model available")
    except Exception as e:  # noqa: BLE001  -> whatever went wrong, the held credits must be released
        return _fail(db, req, e, acc, started)

    return _succeed(db, req, tool, result, acc, started)


def _record_usage_cost(db, req, acc: _Acc, started):
    """Stores provider-reported usage always; cost only when price + FX are known. Returns (usd, idr, pricing, fx)."""
    now = utcnow()
    db.add(AiUsage(request_id=req.id, provider_id=acc.provider.id if acc.provider else None,
                   model_id=acc.model.id if acc.model else None, input_tokens=acc.input, output_tokens=acc.output,
                   cached_tokens=acc.cached, provider_request_id=acc.provider_request_id,
                   latency_ms=int((time.monotonic() - started) * 1000)))
    if not acc.model:
        return None, None, None, None
    p, fx = costing.get_pricing(db, acc.model.id, now), costing.get_fx(db, now)
    idr = acc.usd * fx.rate if (acc.usd is not None and fx) else None
    return acc.usd, idr, p, fx


def _succeed(db, req, tool, result, acc, started):
    usd, idr, p, fx = _record_usage_cost(db, req, acc, started)
    rule = pricing_rule_for(db, tool.slug).to_rule()
    # If the real cost is unknown (price/FX missing) a dynamic charge cannot be computed: charge the held
    # amount, which is never above what the user was shown.
    charge = pricing.charge(rule, idr) if (not rule.needs_api_cost or idr is not None) else req.credits_reserved
    res = credits.settle(db, req.reservation_id, charge)  # capped at the reserved amount
    final = res.amount_final if res.amount_final is not None else Decimal(0)
    db.add(AiCostTracking(request_id=req.id, pricing_id=p.id if p else None, fx_rate_id=fx.id if fx else None,
                          cost_usd=usd, cost_idr=idr, is_estimate=True, credits_charged=final, charge_mode=rule.mode))
    req.output, req.status, req.model_id = result, "succeeded", acc.model.id
    req.credits_charged, req.finished_at = final, utcnow()
    db.commit()
    return req


def _fail(db, req, err, acc, started):
    db.rollback()
    req = db.get(AiRequest, req.id)
    if acc.input or acc.output:  # tokens were spent (e.g. malformed output): the API cost is still ours
        usd, idr, p, fx = _record_usage_cost(db, req, acc, started)
        db.add(AiCostTracking(request_id=req.id, pricing_id=p.id if p else None, fx_rate_id=fx.id if fx else None,
                              cost_usd=usd, cost_idr=idr, is_estimate=True, credits_charged=Decimal(0), charge_mode="failed"))
    credits.release(db, req.reservation_id)  # customer is not charged for a failed generation
    req.status = "failed"
    req.error_code = getattr(err, "code", "internal_error")
    req.credits_charged, req.finished_at = Decimal(0), utcnow()
    db.commit()
    return req
