"""Envelope-less symmetric encryption for provider API keys at rest (Fernet = AES-128-CBC + HMAC).
The master key comes from PROVIDER_KEY_MASTER; rotate by re-encrypting under a new key_id."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

KEY_ID = "v1"


def _fernet() -> Fernet:
    master = get_settings().provider_key_master
    if not master:
        raise RuntimeError("PROVIDER_KEY_MASTER is not set; cannot store or read provider credentials")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest()))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise RuntimeError("provider credential cannot be decrypted (wrong master key?)") from e
