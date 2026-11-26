import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_access_token
from app.users.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(creds.credentials) if creds else None
    if not payload:
        raise HTTPException(401, "not_authenticated")
    request.state.mfa = bool(payload.get("mfa"))
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(401, "not_authenticated")
    return user


def require_roles(*codes: str):
    """Role is checked against the DB (not the token) so revocations apply immediately."""

    def dep(request: Request, user: User = Depends(get_current_user)) -> User:
        if not set(codes) & set(user.role_codes):
            raise HTTPException(403, "forbidden")
        # Admin roles must have signed in with a second factor (switchable only for tests / first-time bootstrap).
        if get_settings().admin_mfa_required and not (user.mfa_enabled and getattr(request.state, "mfa", False)):
            raise HTTPException(403, "mfa_required")
        return user

    return dep


def require_csrf(request: Request) -> None:
    """Cookie-authenticated endpoints (refresh/logout) need a header a cross-site form cannot send, and a same-site Origin."""
    if request.headers.get("x-requested-with") != "fetch":
        raise HTTPException(403, "csrf_blocked")
    origin = request.headers.get("origin")
    if origin:
        s = get_settings()
        allowed = {s.app_base_url.rstrip("/"), *[o.strip().rstrip("/") for o in s.allowed_origins.split(",") if o.strip()]}
        host = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin.rstrip("/") not in allowed and origin.rstrip("/") != host:
            raise HTTPException(403, "csrf_blocked")
