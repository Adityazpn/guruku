from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import mfa as mfa_mod
from app.auth import service
from app.auth.schemas import (
    ForgotIn,
    LoginIn,
    MfaCodeIn,
    MfaSetupOut,
    RegisterIn,
    ResetIn,
    TokenIn,
    TokenOut,
    UserOut,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf
from app.core.rate_limit import rate_limit
from app.core.security import REFRESH_TTL
from app.users.models import User, UserProfile

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"


def _set_cookie(resp: Response, raw: str) -> None:
    resp.set_cookie(
        COOKIE, raw, max_age=int(REFRESH_TTL.total_seconds()), httponly=True,
        secure=get_settings().app_env != "development", samesite="lax", path="/api/v1/auth",
    )


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except service.AuthError as e:
        raise HTTPException(e.status, e.code) from None


def _user_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, full_name=u.full_name, roles=u.role_codes, email_verified=u.email_verified_at is not None, mfa_enabled=u.mfa_enabled)


@router.post("/register", response_model=UserOut, status_code=201, dependencies=[Depends(rate_limit("register", 10))])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    return _user_out(_guard(service.register, db, body.email, body.password, body.full_name))


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("login", 20))])
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    access, raw = _guard(
        service.login, db, body.email, body.password,
        request.client.host if request.client else None, request.headers.get("user-agent"), body.totp,
    )
    _set_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(require_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db),
            refresh_token: str | None = Cookie(default=None)):
    if not refresh_token:
        raise HTTPException(401, "invalid_refresh")
    access, raw = _guard(
        service.refresh, db, refresh_token,
        request.client.host if request.client else None, request.headers.get("user-agent"),
    )
    _set_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def logout(response: Response, db: Session = Depends(get_db), refresh_token: str | None = Cookie(default=None)):
    service.logout(db, refresh_token)
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.post("/verify-email", status_code=204, dependencies=[Depends(rate_limit("verify", 20))])
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    _guard(service.verify_email, db, body.token)


@router.post("/resend-verification", status_code=204, dependencies=[Depends(rate_limit("resend", 3))])
def resend_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.email_verified_at:
        service.send_verification(db, user)


@router.post("/forgot-password", status_code=204, dependencies=[Depends(rate_limit("forgot", 5))])
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    service.forgot_password(db, body.email)


@router.post("/reset-password", status_code=204, dependencies=[Depends(rate_limit("reset", 10))])
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    _guard(service.reset_password, db, body.token, body.new_password)


@router.post("/mfa/setup", response_model=MfaSetupOut, dependencies=[Depends(rate_limit("mfa", 10))])
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(409, "mfa_already_enabled")
    secret = mfa_mod.new_secret()
    mfa_mod.store(user, secret)
    db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=mfa_mod.uri(user, secret))


@router.post("/mfa/confirm", status_code=204, dependencies=[Depends(rate_limit("mfa", 10))])
def mfa_confirm(body: MfaCodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.mfa_enabled or not user.mfa_secret_enc:
        raise HTTPException(409, "mfa_not_pending")
    if not mfa_mod.verify(user, body.code):
        raise HTTPException(400, "invalid_code")
    user.mfa_enabled = True
    db.commit()  # existing sessions keep mfa=false and must sign in again to reach admin routes


me_router = APIRouter(tags=["users"])


@me_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


class ProfileIO(BaseModel):
    school_name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=30)
    province: str = Field(default="", max_length=100)
    education_levels: list[str] = Field(default_factory=list, max_length=10)
    subjects: list[str] = Field(default_factory=list, max_length=30)


def _profile(db: Session, user: User) -> UserProfile:
    p = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if not p:
        p = UserProfile(user_id=user.id)
        db.add(p)
        db.commit()
    return p


@me_router.get("/me/profile", response_model=ProfileIO)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _profile(db, user)
    return ProfileIO.model_validate(p, from_attributes=True)


@me_router.put("/me/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _profile(db, user)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return body
