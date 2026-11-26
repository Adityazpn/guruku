from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import EmailToken, UserSession
from app.core.config import get_settings
from app.core.db import utcnow
from app.core.email import send_email
from app.core.security import (
    REFRESH_TTL,
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.credits import service as credits
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
    credits.grant_trial(db, user.id)
    db.commit()
    send_verification(db, user)
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


VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)


def _make_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    # invalidate earlier unused tokens of the same purpose
    for t in db.scalars(
        select(EmailToken).where(
            EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None)
        )
    ):
        t.used_at = utcnow()
    raw, hashed = new_refresh_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=hashed, expires_at=utcnow() + ttl))
    db.commit()
    return raw


def _consume(db: Session, raw: str, purpose: str) -> User:
    t = db.scalar(
        select(EmailToken).where(EmailToken.token_hash == hash_token(raw), EmailToken.purpose == purpose).with_for_update()
    )
    if not t or t.used_at is not None or _aware(t.expires_at) <= utcnow():
        raise AuthError("invalid_token", 400)
    user = db.get(User, t.user_id)
    if not user:
        raise AuthError("invalid_token", 400)
    t.used_at = utcnow()
    return user


def send_verification(db: Session, user: User) -> None:
    raw = _make_token(db, user, "verify", VERIFY_TTL)
    link = f"{get_settings().app_base_url}/verify-email?token={raw}"
    send_email(user.email, "Verifikasi email Anda", f"Klik tautan berikut untuk memverifikasi email:\n{link}\n\nTautan berlaku 24 jam.")


def verify_email(db: Session, raw: str) -> None:
    user = _consume(db, raw, "verify")
    user.email_verified_at = user.email_verified_at or utcnow()
    db.commit()


def forgot_password(db: Session, email: str) -> None:
    """Always returns silently so callers cannot learn which emails exist."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or user.status != "active":
        return
    raw = _make_token(db, user, "reset", RESET_TTL)
    link = f"{get_settings().app_base_url}/reset-password?token={raw}"
    send_email(user.email, "Atur ulang kata sandi", f"Klik tautan berikut untuk mengatur ulang kata sandi:\n{link}\n\nTautan berlaku 1 jam. Abaikan jika bukan Anda yang meminta.")


def reset_password(db: Session, raw: str, new_password: str) -> None:
    user = _consume(db, raw, "reset")
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)):
        s.revoked_at = s.revoked_at or utcnow()
    db.commit()
