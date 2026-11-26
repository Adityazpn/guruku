from fastapi import Request
from sqlalchemy.orm import Session

from app.admin.models import AuditLog

SECRET_KEYS = {"api_key", "secret", "password", "token", "secret_ciphertext"}


def _clean(d):
    if isinstance(d, dict):
        return {k: ("***" if k in SECRET_KEYS else _clean(v)) for k, v in d.items()}
    if isinstance(d, list):
        return [_clean(x) for x in d]
    return d if d is None or isinstance(d, (str, int, float, bool)) else str(d)


def audit(db: Session, actor, action: str, entity_type: str, entity_id, *, before=None, after=None,
          request: Request | None = None) -> None:
    """Written in the same transaction as the change it describes, so they commit or roll back together."""
    db.add(AuditLog(actor_id=actor.id, action=action, entity_type=entity_type, entity_id=str(entity_id),
                    before=_clean(before), after=_clean(after),
                    ip=(request.client.host if request and request.client else None)))
