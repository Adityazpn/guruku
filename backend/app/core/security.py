import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
_hasher = PasswordHasher()  # argon2id defaults
_ephemeral_key = secrets.token_urlsafe(48)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _secret() -> str:
    s = get_settings()
    if s.secret_key:
        return s.secret_key
    if s.app_env != "development":
        raise RuntimeError("SECRET_KEY must be set outside development")
    return _ephemeral_key


def create_access_token(user_id: str, roles: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {"sub": user_id, "roles": roles, "iat": now, "exp": now + ACCESS_TTL, "typ": "access"}
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return data if data.get("typ") == "access" else None


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
