"""TOTP second factor (RFC 6238) for admin accounts. The secret is stored encrypted (same envelope as provider keys)."""
import pyotp

from app.core.crypto import decrypt_secret, encrypt_secret
from app.users.models import User

ISSUER = "Guruku"


def new_secret() -> str:
    return pyotp.random_base32()


def store(user: User, secret: str) -> None:
    user.mfa_secret_enc = encrypt_secret(secret)
    user.mfa_enabled = False  # enabled only after the user proves they can generate a code


def uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)


def verify(user: User, code: str) -> bool:
    if not user.mfa_secret_enc or not code or not code.strip().isdigit():
        return False
    return pyotp.TOTP(decrypt_secret(user.mfa_secret_enc)).verify(code.strip(), valid_window=1)
