"""Security module for Mnemo.

Handles API Key encryption at rest.
"""
import os
from pathlib import Path
from cryptography.fernet import Fernet
import structlog

logger = structlog.get_logger()

# Path to the local secret key
SECRET_KEY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / ".mnemo_secret"

def _get_fernet_key() -> bytes:
    if not SECRET_KEY_PATH.exists():
        SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
        logger.info("security.key_generated", path=str(SECRET_KEY_PATH))
    return SECRET_KEY_PATH.read_bytes()

_fernet = Fernet(_get_fernet_key())

def encrypt_value(value: str) -> str:
    """Encrypt a string value."""
    if not value:
        return value
    return _fernet.encrypt(value.encode()).decode()

def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a string value."""
    if not encrypted_value:
        return encrypted_value
    try:
        return _fernet.decrypt(encrypted_value.encode()).decode()
    except Exception as e:
        logger.error("security.decrypt_failed", error=str(e))
        return encrypted_value
