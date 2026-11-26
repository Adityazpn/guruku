import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from jinja2 import TemplateSyntaxError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.admin import schemas as s
from app.admin.audit import audit
from app.admin.models import AuditLog
from app.ai_engine.engine import _jinja, pricing_rule_for
from app.ai_engine.models import AiCostTracking, AiPromptVersion, AiRequest, AiTool, AiUsage
from app.ai_providers import costing
from app.ai_providers.base import LLMRequest, ProviderError
from app.ai_providers.models import (
    AiModel,
    AiModelPricing,
    AiProvider,
    AiProviderCredential,
    AiToolModelAssignment,
    FxRate,
)
from app.ai_providers.registry import ADAPTERS, build_adapter, resolve_api_key
from app.core.config import get_settings
from app.core.crypto import KEY_ID, encrypt_secret
from app.core.db import get_db, utcnow
from app.core.deps import require_roles
from app.core.rate_limit import rate_limit
from app.credits import service as credits
from app.credits.models import BucketType, TxType
from app.credits.pricing_models import CreditPricingRule
from app.users.models import User

# Every route needs a role; writes are audit-logged in the same transaction.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("super_admin", "ai_admin"))])
root_only = Depends(require_roles("super_admin"))
ai_admin = Depends(require_roles("super_admin", "ai_admin"))


def _get(db, model, id_, code="not_found"):
    row = db.get(model, id_)
    if row is None:
        raise HTTPException(404, code)
    return row


def _f(x):
    return None if x is None else float(x)


# ------------------------------------------------------------------ providers
def _spend(db: Session, provider_id, since) -> float:
    v = db.scalar(select(func.coalesce(func.sum(AiCostTracking.cost_usd), 0)).join(AiUsage, AiUsage.request_id == AiCostTracking.request_id)
                  .where(AiUsage.provider_id == provider_id, AiCostTracking.created_at >= since))
    return float(v or 0)


def _provider_out(db: Session, p: AiProvider) -> dict:
    now = utcnow()
    cred = db.scalar(select(AiProviderCredential).where(AiProviderCredential.provider_id == p.id)
                     .order_by(AiProviderCredential.created_at.desc()))
    models = []
    for m in db.scalars(select(AiModel).where(AiModel.provider_id == p.id).order_by(AiModel.model_code)):
        pr = costing.get_pricing(db, m.id, now)
        models.append({"id": str(m.id), "model_code": m.model_code, "display_name": m.display_name, "status": m.status,
                       "max_output_tokens": m.max_output_tokens,
                       "pricing": None if pr is None else {"version": pr.version, "input_per_1m": _f(pr.input_per_1m), "output_per_1m": _f(pr.output_per_1m),
                                                           "cached_input_per_1m": _f(pr.cached_input_per_1m), "currency": pr.currency}})
    return {"id": str(p.id), "code": p.code, "name": p.name, "status": p.status, "base_url": p.base_url,
            "daily_spend_limit_usd": _f(p.daily_spend_limit_usd), "monthly_spend_limit_usd": _f(p.monthly_spend_limit_usd),
            "credential": None if cred is None else {"label": cred.label, "last4": cred.last4, "status": cred.status},  # never the key
            "env_key_present": bool(__import__("os").environ.get(f"{p.code.upper()}_API_KEY")),
            "spend_today_usd": _spend(db, p.id, now.replace(hour=0, minute=0, second=0, microsecond=0)),
            "spend_month_usd": _spend(db, p.id, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),
            "spend_is_estimate": True, "models": models}


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    fx = costing.get_fx(db, utcnow())
    return {"providers": [_provider_out(db, p) for p in db.scalars(select(AiProvider).order_by(AiProvider.code))],
            "supported_codes": sorted(c for c in ADAPTERS if c != "fake" or get_settings().app_env == "development"),
            "fx": None if fx is None else {"rate": _f(fx.rate), "effective_from": fx.effective_from}}


@router.post("/providers", status_code=201)
def create_provider(body: s.ProviderIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    if body.code not in ADAPTERS or (body.code == "fake" and get_settings().app_env != "development"):
        raise HTTPException(422, "unsupported_provider")
    if db.scalar(select(AiProvider).where(AiProvider.code == body.code)):
        raise HTTPException(409, "provider_exists")
    p = AiProvider(code=body.code, name=body.name, base_url=body.base_url, status="disabled")
    db.add(p)
    db.flush()
    audit(db, user, "provider.create", "provider", p.id, after={"code": p.code, "name": p.name}, request=request)
    db.commit()
    return _provider_out(db, p)


@router.patch("/providers/{pid}")
def patch_provider(pid: uuid.UUID, body: s.ProviderPatch, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    p = _get(db, AiProvider, pid)
    before = {"status": p.status, "daily": _f(p.daily_spend_limit_usd), "monthly": _f(p.monthly_spend_limit_usd)}
    if body.status == "enabled" and p.code != "fake":
        key, _ = resolve_api_key(db, p)
        if not key:
            raise HTTPException(409, "no_credential")  # refuse to enable a provider that cannot authenticate
    for f in ("name", "status", "base_url"):
        v = getattr(body, f)
        if v is not None:
            setattr(p, f, v)
    if body.clear_limits:
        p.daily_spend_limit_usd = p.monthly_spend_limit_usd = None
    if body.daily_spend_limit_usd is not None:
        p.daily_spend_limit_usd = body.daily_spend_limit_usd
    if body.monthly_spend_limit_usd is not None:
        p.monthly_spend_limit_usd = body.monthly_spend_limit_usd
    audit(db, user, "provider.update", "provider", p.id, before=before,
          after={"status": p.status, "daily": _f(p.daily_spend_limit_usd), "monthly": _f(p.monthly_spend_limit_usd)}, request=request)
    db.commit()
    return _provider_out(db, p)


@router.put("/providers/{pid}/credential")
def set_credential(pid: uuid.UUID, body: s.CredentialIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    """Write-only: the key is encrypted immediately and can never be read back through the API."""
    p = _get(db, AiProvider, pid)
    key = body.api_key.strip()
    for old in db.scalars(select(AiProviderCredential).where(AiProviderCredential.provider_id == p.id, AiProviderCredential.status == "active")):
        old.status = "revoked"
    c = AiProviderCredential(provider_id=p.id, label=body.label, secret_ciphertext=encrypt_secret(key), key_id=KEY_ID, last4=key[-4:])
    db.add(c)
    db.flush()
    audit(db, user, "provider.credential.set", "provider", p.id, after={"label": body.label, "last4": c.last4}, request=request)
    db.commit()
    return _provider_out(db, p)


@router.post("/providers/{pid}/test", dependencies=[Depends(rate_limit("provider_test", 5))])
def test_provider(pid: uuid.UUID, body: s.TestIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    """One tiny real call (costs a fraction of a cent) to confirm the key and model id work."""
    p = _get(db, AiProvider, pid)
    m = _get(db, AiModel, uuid.UUID(body.model_id))
    if m.provider_id != p.id:
        raise HTTPException(422, "model_not_of_provider")
    try:
        key, cred = resolve_api_key(db, p)
        out = build_adapter(p, key).generate(LLMRequest(model=m.model_code, system="Balas hanya dengan JSON.",
                                                       user='Balas dengan {"ok": true}', max_tokens=50, temperature=0, timeout_s=30))
        res = {"ok": True, "input_tokens": out.input_tokens, "output_tokens": out.output_tokens}
    except ProviderError as e:
        res = {"ok": False, "error": e.code}
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": type(e).__name__}
    audit(db, user, "provider.test", "provider", p.id, after={"model": m.model_code, **res}, request=request)
    db.commit()
    return res


@router.post("/providers/{pid}/models", status_code=201)
def add_model(pid: uuid.UUID, body: s.ModelIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    p = _get(db, AiProvider, pid)
    if db.scalar(select(AiModel).where(AiModel.provider_id == p.id, AiModel.model_code == body.model_code)):
        raise HTTPException(409, "model_exists")
    m = AiModel(provider_id=p.id, model_code=body.model_code, display_name=body.display_name or body.model_code,
                max_output_tokens=body.max_output_tokens)
    db.add(m)
    db.flush()
    audit(db, user, "model.create", "model", m.id, after={"provider": p.code, "model": m.model_code}, request=request)
    db.commit()
    return _provider_out(db, p)


@router.patch("/models/{mid}")
def patch_model(mid: uuid.UUID, body: s.ModelPatch, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    m = _get(db, AiModel, mid)
    before = {"status": m.status, "max_output_tokens": m.max_output_tokens}
    for f in ("display_name", "status", "max_output_tokens"):
        v = getattr(body, f)
        if v is not None:
            setattr(m, f, v)
    audit(db, user, "model.update", "model", m.id, before=before, after={"status": m.status, "max_output_tokens": m.max_output_tokens}, request=request)
    db.commit()
    return _provider_out(db, db.get(AiProvider, m.provider_id))


@router.post("/models/{mid}/pricing", status_code=201)
def add_pricing(mid: uuid.UUID, body: s.PricingIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    """New price version; the previous one is closed, never edited (history keeps explaining past costs)."""
    m = _get(db, AiModel, mid)
    start = body.effective_from or utcnow()
    prev = db.scalar(select(AiModelPricing).where(AiModelPricing.model_id == m.id).order_by(AiModelPricing.effective_from.desc()))
    if prev and start <= (prev.effective_from if prev.effective_from.tzinfo else prev.effective_from.replace(tzinfo=start.tzinfo)):
        raise HTTPException(422, "effective_from_must_be_after_previous")
    if prev:
        prev.effective_to = start
    row = AiModelPricing(model_id=m.id, version=(prev.version + 1) if prev else 1, input_per_1m=body.input_per_1m,
                         output_per_1m=body.output_per_1m, cached_input_per_1m=body.cached_input_per_1m, effective_from=start)
    db.add(row)
    db.flush()
    audit(db, user, "pricing.create", "model", m.id, before=None if not prev else {"input": _f(prev.input_per_1m), "output": _f(prev.output_per_1m)},
          after={"version": row.version, "input": _f(row.input_per_1m), "output": _f(row.output_per_1m)}, request=request)
    db.commit()
    return _provider_out(db, db.get(AiProvider, m.provider_id))


@router.post("/fx-rates", status_code=201)
def add_fx(body: s.FxIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    fx = FxRate(rate=body.rate, effective_from=body.effective_from or utcnow())
    db.add(fx)
    db.flush()
    audit(db, user, "fx.create", "fx_rate", fx.id, after={"rate": _f(fx.rate)}, request=request)
    db.commit()
    return {"rate": _f(fx.rate), "effective_from": fx.effective_from}


# ------------------------------------------------------------------ tools / prompts / credit pricing
def _tool_out(db: Session, t: AiTool) -> dict:
    now = utcnow()
    rows = db.execute(select(AiModel, AiProvider).join(AiToolModelAssignment, AiToolModelAssignment.model_id == AiModel.id)
                      .join(AiProvider, AiProvider.id == AiModel.provider_id).where(AiToolModelAssignment.tool_id == t.id)
                      .order_by(AiToolModelAssignment.priority)).all()
    rule = pricing_rule_for(db, t.slug)
    ver = db.scalar(select(AiPromptVersion).where(AiPromptVersion.tool_id == t.id, AiPromptVersion.status == "published")
                    .order_by(AiPromptVersion.version.desc()))
    fx = costing.get_fx(db, now)
    problems = []
    if not ver:
        problems.append("no_published_prompt")
    if rule is None:
        problems.append("no_pricing_rule")
    usable = [(m, p) for m, p in rows if m.status == "active" and p.status == "enabled"]
    if not usable:
        problems.append("no_enabled_model")
    if rule is not None and rule.mode != "fixed":
        if fx is None:
            problems.append("no_fx_rate")
        if usable and costing.get_pricing(db, usable[0][0].id, now) is None:
            problems.append("no_model_price")
    return {"id": str(t.id), "slug": t.slug, "name": t.name, "category": t.category, "description": t.description, "is_active": t.is_active,
            "est_input_tokens": t.est_input_tokens, "est_output_tokens": t.est_output_tokens, "max_output_tokens": t.max_output_tokens,
            "models": [{"id": str(m.id), "model_code": m.model_code, "provider": p.code, "status": m.status} for m, p in rows],
            "published_prompt_version": ver.version if ver else None,
            "pricing_rule": None if rule is None else {"version": rule.version, **{k: (str(getattr(rule, k)) if k != "mode" else rule.mode) for k in (
                "mode", "fixed_credits", "base_credits", "margin_pct", "processing_fee_idr", "credit_value_idr", "rounding_step",
                "min_credits", "max_credits", "reserve_safety_factor")}},
            "ready": not problems, "problems": problems}


@router.get("/tools")
def admin_tools(db: Session = Depends(get_db)):
    return [_tool_out(db, t) for t in db.scalars(select(AiTool).order_by(AiTool.sort, AiTool.name))]


@router.patch("/tools/{tid}")
def patch_tool(tid: uuid.UUID, body: s.ToolPatch, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    t = _get(db, AiTool, tid)
    changes = body.model_dump(exclude_none=True)
    before = {k: getattr(t, k) for k in changes}
    for k, v in changes.items():
        setattr(t, k, v)
    audit(db, user, "tool.update", "tool", t.id, before=before, after=changes, request=request)
    db.commit()
    return _tool_out(db, t)


@router.put("/tools/{tid}/assignments")
def set_assignments(tid: uuid.UUID, body: s.AssignIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    t = _get(db, AiTool, tid)
    ids = [uuid.UUID(x) for x in body.model_ids]
    if len(set(ids)) != len(ids) or any(db.get(AiModel, i) is None for i in ids):
        raise HTTPException(422, "invalid_models")
    old = [str(a.model_id) for a in db.scalars(select(AiToolModelAssignment).where(AiToolModelAssignment.tool_id == t.id).order_by(AiToolModelAssignment.priority))]
    for a in db.scalars(select(AiToolModelAssignment).where(AiToolModelAssignment.tool_id == t.id)):
        db.delete(a)
    db.flush()
    for i, mid in enumerate(ids):
        db.add(AiToolModelAssignment(tool_id=t.id, model_id=mid, priority=i))
    audit(db, user, "tool.assign_models", "tool", t.id, before={"models": old}, after={"models": body.model_ids}, request=request)
    db.commit()
    return _tool_out(db, t)


@router.put("/tools/{tid}/pricing-rule")
def set_pricing_rule(tid: uuid.UUID, body: s.PricingRuleIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    t = _get(db, AiTool, tid)
    prev = db.scalar(select(CreditPricingRule).where(CreditPricingRule.tool_slug == t.slug, CreditPricingRule.active.is_(True))
                     .order_by(CreditPricingRule.version.desc()))
    if prev:
        prev.active = False
    row = CreditPricingRule(tool_slug=t.slug, version=(prev.version + 1) if prev else 1, active=True, **body.model_dump())
    db.add(row)
    audit(db, user, "pricing_rule.set", "tool", t.id, before=None if not prev else {"mode": prev.mode, "version": prev.version},
          after=body.model_dump(mode="json"), request=request)
    db.commit()
    return _tool_out(db, t)


def _prompt_out(v: AiPromptVersion) -> dict:
    return {"id": str(v.id), "version": v.version, "status": v.status, "system_prompt": v.system_prompt, "user_template": v.user_template,
            "temperature": _f(v.temperature), "change_note": v.change_note, "created_at": v.created_at}


@router.get("/tools/{tid}/prompts")
def list_prompts(tid: uuid.UUID, db: Session = Depends(get_db)):
    _get(db, AiTool, tid)
    return [_prompt_out(v) for v in db.scalars(select(AiPromptVersion).where(AiPromptVersion.tool_id == tid).order_by(AiPromptVersion.version.desc()))]


def _check_template(src: str):
    try:
        _jinja.from_string(src)
    except TemplateSyntaxError as e:
        raise HTTPException(422, f"template_syntax: {e.message}") from None


def _next_version(db, tid) -> int:
    return (db.scalar(select(func.max(AiPromptVersion.version)).where(AiPromptVersion.tool_id == tid)) or 0) + 1


def _publish(db, tid, v: AiPromptVersion):
    for old in db.scalars(select(AiPromptVersion).where(AiPromptVersion.tool_id == tid, AiPromptVersion.status == "published")):
        old.status = "archived"
    v.status = "published"


@router.post("/tools/{tid}/prompts", status_code=201)
def create_prompt(tid: uuid.UUID, body: s.PromptIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    """Always a new DRAFT version. Published versions are immutable (there is no edit endpoint)."""
    _get(db, AiTool, tid)
    _check_template(body.user_template)
    v = AiPromptVersion(tool_id=tid, version=_next_version(db, tid), system_prompt=body.system_prompt, user_template=body.user_template,
                        temperature=body.temperature, change_note=body.change_note, status="draft")
    db.add(v)
    db.flush()
    audit(db, user, "prompt.create", "tool", tid, after={"version": v.version}, request=request)
    db.commit()
    return _prompt_out(v)


@router.post("/prompts/{vid}/publish")
def publish_prompt(vid: uuid.UUID, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    v = _get(db, AiPromptVersion, vid)
    if v.status == "archived":
        raise HTTPException(409, "archived_version_use_rollback")
    if v.status != "published":
        _publish(db, v.tool_id, v)
        audit(db, user, "prompt.publish", "tool", v.tool_id, after={"version": v.version}, request=request)
        db.commit()
    return _prompt_out(v)


@router.post("/tools/{tid}/prompts/rollback")
def rollback_prompt(tid: uuid.UUID, body: s.RollbackIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    """Re-publishes an older version's content as a NEW version, so history is never rewritten."""
    src = db.scalar(select(AiPromptVersion).where(AiPromptVersion.tool_id == tid, AiPromptVersion.version == body.version))
    if src is None:
        raise HTTPException(404, "not_found")
    v = AiPromptVersion(tool_id=tid, version=_next_version(db, tid), system_prompt=src.system_prompt, user_template=src.user_template,
                        temperature=src.temperature, change_note=f"rollback to v{src.version}", status="draft")
    db.add(v)
    db.flush()
    _publish(db, tid, v)
    audit(db, user, "prompt.rollback", "tool", tid, after={"from": src.version, "new_version": v.version}, request=request)
    db.commit()
    return _prompt_out(v)


# ------------------------------------------------------------------ usage / cost
@router.get("/ai/usage")
def usage(days: int = Query(30, ge=1, le=366), db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=days)
    ok = func.sum(case((AiRequest.status == "succeeded", 1), else_=0))
    bad = func.sum(case((AiRequest.status == "failed", 1), else_=0))
    rows = db.execute(
        select(AiTool.slug, AiModel.model_code, func.count(AiRequest.id), ok, bad, func.coalesce(func.sum(AiUsage.input_tokens), 0),
               func.coalesce(func.sum(AiUsage.output_tokens), 0), func.sum(AiCostTracking.cost_usd), func.sum(AiCostTracking.cost_idr),
               func.coalesce(func.sum(AiRequest.credits_charged), 0))
        .join(AiTool, AiTool.id == AiRequest.tool_id)
        .outerjoin(AiUsage, AiUsage.request_id == AiRequest.id).outerjoin(AiModel, AiModel.id == AiUsage.model_id)
        .outerjoin(AiCostTracking, AiCostTracking.request_id == AiRequest.id)
        .where(AiRequest.created_at >= since).group_by(AiTool.slug, AiModel.model_code).order_by(AiTool.slug)).all()
    items = [{"tool": a, "model": b, "requests": c, "succeeded": int(d or 0), "failed": int(e or 0), "input_tokens": int(f), "output_tokens": int(g),
              "api_cost_usd": _f(h), "api_cost_idr": _f(i), "credits_charged": _f(j)} for a, b, c, d, e, f, g, h, i, j in rows]
    tot = lambda k: sum((x[k] or 0) for x in items)  # noqa: E731
    return {"days": days, "is_estimate": True,  # costs are computed from provider-reported usage x configured prices, not invoices
            "totals": {"requests": tot("requests"), "failed": tot("failed"), "api_cost_usd": tot("api_cost_usd"),
                       "api_cost_idr": tot("api_cost_idr"), "credits_charged": tot("credits_charged")}, "items": items}


# ------------------------------------------------------------------ users / credits / audit (super_admin only)
@router.get("/users", dependencies=[root_only])
def search_users(q: str = Query("", max_length=100), db: Session = Depends(get_db)):
    qs = select(User).order_by(User.created_at.desc()).limit(20)
    if q:
        qs = qs.where(User.email.ilike(f"%{q.lower()}%"))
    out = []
    for u in db.scalars(qs):
        w = credits.get_or_create_wallet(db, u.id)
        out.append({"id": str(u.id), "email": u.email, "full_name": u.full_name, "status": u.status, "roles": u.role_codes,
                    "credits": str(credits.summary(db, w.id)["total"])})
    db.commit()
    return out


@router.post("/users/{uid}/credits/grant", status_code=201, dependencies=[root_only])
def grant_credits(uid: uuid.UUID, body: s.GrantIn, request: Request, user: User = ai_admin, db: Session = Depends(get_db)):
    target = _get(db, User, uid)
    w = credits.get_or_create_wallet(db, target.id)
    exp = utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    kind = BucketType.bonus
    credits.grant(db, w, bucket_type=kind, amount=body.amount, source_type="admin", source_id=str(uuid.uuid4()),
                  tx_type=TxType.bonus if body.kind == "bonus" else TxType.promotional, expires_at=exp,
                  description=f"Admin grant: {body.reason}", actor_id=user.id)
    audit(db, user, "credits.grant", "user", target.id, after={"amount": str(body.amount), "kind": body.kind, "reason": body.reason}, request=request)
    db.commit()
    return {"total": str(credits.summary(db, w.id)["total"])}


@router.get("/audit-logs", dependencies=[root_only])
def audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), action: str | None = None, db: Session = Depends(get_db)):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "items": [{"id": str(a.id), "actor_id": str(a.actor_id) if a.actor_id else None, "action": a.action,
                                                      "entity_type": a.entity_type, "entity_id": a.entity_id, "before": a.before, "after": a.after,
                                                      "ip": a.ip, "created_at": a.created_at} for a in rows]}




@router.get("/system")
def system_health(db: Session = Depends(get_db)):
    """Operational snapshot for the admin: is anything stuck, failing or silently losing money?"""
    from app.payments.models import PaymentOrder, PaymentWebhook

    now = utcnow()
    n = lambda q: db.scalar(q) or 0  # noqa: E731
    stats = {
        "ai_queued": n(select(func.count()).select_from(AiRequest).where(AiRequest.status == "queued")),
        "ai_queued_over_5min": n(select(func.count()).select_from(AiRequest).where(AiRequest.status == "queued", AiRequest.created_at <= now - timedelta(minutes=5))),
        "ai_running_over_15min": n(select(func.count()).select_from(AiRequest).where(AiRequest.status == "running", AiRequest.started_at <= now - timedelta(minutes=15))),
        "ai_failed_last_hour": n(select(func.count()).select_from(AiRequest).where(AiRequest.status == "failed", AiRequest.created_at >= now - timedelta(hours=1))),
        "ai_total_last_hour": n(select(func.count()).select_from(AiRequest).where(AiRequest.created_at >= now - timedelta(hours=1))),
        "webhook_problems_24h": n(select(func.count()).select_from(PaymentWebhook).where(
            PaymentWebhook.received_at >= now - timedelta(hours=24),
            (PaymentWebhook.process_status.like("error:%")) | (PaymentWebhook.process_status.like("rejected:%")))),
        "orders_pending_over_1day": n(select(func.count()).select_from(PaymentOrder).where(PaymentOrder.status == "pending", PaymentOrder.created_at <= now - timedelta(days=1))),
        "invalid_provider_keys": n(select(func.count()).select_from(AiProviderCredential).where(AiProviderCredential.status == "invalid")),
    }
    alerts = []
    if stats["ai_queued_over_5min"]:
        alerts.append("Ada permintaan AI antre >5 menit: periksa worker Celery.")
    if stats["ai_running_over_15min"]:
        alerts.append("Ada permintaan AI 'running' >15 menit: worker mungkin mati.")
    if stats["ai_total_last_hour"] >= 10 and stats["ai_failed_last_hour"] / stats["ai_total_last_hour"] > 0.3:
        alerts.append("Lebih dari 30% generate gagal dalam 1 jam terakhir.")
    if stats["webhook_problems_24h"]:
        alerts.append("Ada webhook pembayaran bermasalah/ditolak dalam 24 jam: lihat Pembayaran > Webhook.")
    if stats["invalid_provider_keys"]:
        alerts.append("API key penyedia AI ditolak (invalid): ganti key di Provider AI.")
    return {"stats": stats, "alerts": alerts}
