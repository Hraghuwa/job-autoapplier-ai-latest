import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from backend.config import settings

logger = logging.getLogger(__name__)

# All Fernet tokens are base64url of a payload whose first byte is the version
# 0x80, which encodes to the literal prefix "gAAAAA". We use this to tell a
# real (but undecryptable) ciphertext apart from genuine legacy plaintext.
_FERNET_PREFIX = "gAAAAA"


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
    looks_encrypted = ciphertext.startswith(_FERNET_PREFIX)
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        if looks_encrypted:
            # A real Fernet token we cannot decrypt → wrong/rotated key or
            # corruption. Returning the ciphertext here would type base64 gibberish
            # into login forms and mask key-rotation problems. Fail loud, fail empty.
            logger.error("decrypt: Fernet token failed to decrypt (wrong/rotated FERNET_KEY?). "
                         "Returning empty so callers don't use ciphertext as a credential.")
            return ""
        return ciphertext  # genuinely legacy plaintext (predates encryption)
    except Exception:
        # Key not configured or other error. Only pass through if it isn't a token.
        if looks_encrypted:
            logger.error("decrypt: could not decrypt an encrypted value; returning empty.")
            return ""
        return ciphertext


def encrypt_dict(d: dict) -> dict:
    """Encrypt every string value in a dict."""
    return {k: encrypt(v) if isinstance(v, str) else v for k, v in d.items()}


def decrypt_dict(d: dict) -> dict:
    """Decrypt every string value in a dict."""
    return {k: decrypt(v) if isinstance(v, str) else v for k, v in d.items()}
