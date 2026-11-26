from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import REFRESH_TTL
from app.users.models import User

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
        raise HTTPException(e.status, e.code)


def _user_out(u: User) -> UserOut:
    return UserOut(id=str(u.id), email=u.email, full_name=u.full_name, roles=u.role_codes)


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    return _user_out(_guard(service.register, db, body.email, body.password, body.full_name))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    access, raw = _guard(
        service.login, db, body.email, body.password,
        request.client.host if request.client else None, request.headers.get("user-agent"),
    )
    _set_cookie(response, raw)
    return TokenOut(access_token=access)


@router.post("/refresh", response_model=TokenOut)
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


@router.post("/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), refresh_token: str | None = Cookie(default=None)):
    service.logout(db, refresh_token)
    response.delete_cookie(COOKIE, path="/api/v1/auth")


me_router = APIRouter(tags=["users"])


@me_router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
