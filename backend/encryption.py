import os
import warnings
from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("SECRET_KEY")
        if not key:
            warnings.warn(
                "SECRET_KEY env var not set — generating ephemeral key. "
                "Encrypted data will be unreadable after restart. "
                "Set SECRET_KEY to a stable Fernet key in production.",
                RuntimeWarning,
                stacklevel=3,
            )
            key = Fernet.generate_key().decode()
            os.environ["SECRET_KEY"] = key
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _get_fernet().decrypt(token.encode()).decode()


def generate_webhook_secret(length: int = 32) -> str:
    return os.urandom(length).hex()
