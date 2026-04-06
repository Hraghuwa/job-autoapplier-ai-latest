from typing import Optional
from cryptography.fernet import Fernet
from backend.config import settings


def _fernet() -> Fernet:
    key = settings.fernet_key
    if not key or key == "CHANGE_ME_FERNET_KEY":
        raise RuntimeError(
            "FERNET_KEY not configured in backend/.env — "
            "generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext  # already plaintext (legacy / unencrypted)


def encrypt_dict(d: dict) -> dict:
    """Encrypt every string value in a dict."""
    return {k: encrypt(v) if isinstance(v, str) else v for k, v in d.items()}


def decrypt_dict(d: dict) -> dict:
    """Decrypt every string value in a dict."""
    return {k: decrypt(v) if isinstance(v, str) else v for k, v in d.items()}
