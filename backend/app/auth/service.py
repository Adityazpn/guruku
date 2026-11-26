from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.db import utcnow
from app.core.security import (
    REFRESH_TTL,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.users.models import Role, User, UserRole

MAX_FAILED = 5
LOCK_FOR = timedelta(minutes=15)
# Verified against when the email is unknown, so timing does not reveal account existence.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class AuthError(Exception):
    def __init__(self, code: str, status: int = 401):
        self.code, self.status = code, status


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; Postgres returns aware ones.
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=utcnow().tzinfo)
    return dt


def get_or_create_role(db: Session, code: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        role = Role(code=code)
        db.add(role)
        db.flush()
    return role


def register(db: Session, email: str, password: str, full_name: str) -> User:
    email = email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise AuthError("email_taken", 409)
    user = User(email=email, password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    db.flush()
    user.roles.append(UserRole(user_id=user.id, role=get_or_create_role(db, "user")))
    db.commit()
    return user


def _issue(db: Session, user: User, ip, ua, rotated_from=None) -> tuple[str, str]:
    raw, hashed = new_refresh_token()
    db.add(
        UserSession(
            user_id=user.id,
            refresh_token_hash=hashed,
            ip=ip,
            user_agent=(ua or "")[:300],
            expires_at=utcnow() + REFRESH_TTL,
            rotated_from=rotated_from,
        )
    )
    db.commit()
    return create_access_token(str(user.id), user.role_codes), raw


def login(db: Session, email: str, password: str, ip=None, ua=None) -> tuple[str, str]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        verify_password(password, _DUMMY_HASH)
        raise AuthError("invalid_credentials")
    now = utcnow()
    if (lu := _aware(user.locked_until)) and lu > now:
        raise AuthError("account_locked", 423)
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED:
            user.locked_until = now + LOCK_FOR
            user.failed_login_count = 0
        db.commit()
        raise AuthError("invalid_credentials")
    if user.status != "active":
        raise AuthError("account_disabled", 403)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    return _issue(db, user, ip, ua)


def refresh(db: Session, raw_token: str, ip=None, ua=None) -> tuple[str, str]:
    sess = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_token)).with_for_update()
    )
    if not sess:
        raise AuthError("invalid_refresh")
    if sess.revoked_at is not None:
        # Reuse of a rotated token => assume theft, revoke every session of this user.
        for s in db.scalars(select(UserSession).where(UserSession.user_id == sess.user_id)):
            s.revoked_at = s.revoked_at or utcnow()
        db.commit()
        raise AuthError("refresh_reuse_detected")
    if _aware(sess.expires_at) <= utcnow():
        raise AuthError("invalid_refresh")
    user = db.get(User, sess.user_id)
    if not user or user.status != "active":
        raise AuthError("account_disabled", 403)
    sess.revoked_at = utcnow()
    return _issue(db, user, ip, ua, rotated_from=sess.id)


def logout(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(raw_token)))
    if sess and sess.revoked_at is None:
        sess.revoked_at = utcnow()
        db.commit()
