import uuid

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.users.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(creds.credentials) if creds else None
    if not payload:
        raise HTTPException(401, "not_authenticated")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(401, "not_authenticated")
    return user


def require_roles(*codes: str):
    """Role is checked against the DB (not the token) so revocations apply immediately."""

    def dep(user: User = Depends(get_current_user)) -> User:
        if not set(codes) & set(user.role_codes):
            raise HTTPException(403, "forbidden")
        return user

    return dep
