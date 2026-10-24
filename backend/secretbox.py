"""Encrypt secrets we must store and use later, such as a customer's Twilio auth token or AI API key.

Uses ENCRYPTION_KEY (any long random string). Falls back to JWT_SECRET so existing servers
keep working, but set ENCRYPTION_KEY in production and never change it: secrets encrypted
with a key that's gone can't be read back. When both are set, values encrypted with either
can be read (new ones use ENCRYPTION_KEY), so adding ENCRYPTION_KEY later is safe.

`EncryptedText` is a column type that does this transparently: values are encrypted on the
way into the database and decrypted on the way out. Rows saved before encryption existed
(plain text) are still read, and are converted at startup (database._encrypt_legacy_secrets).
"""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import Text, TypeDecorator

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"  # marks values stored by EncryptedText


class SecretError(Exception):
    pass


def _key(material: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest()))


def _fernet() -> MultiFernet:
    """The first key encrypts; every key can decrypt. ENCRYPTION_OLD_KEYS (comma-separated) lists keys
    that were replaced, so secrets saved under them can still be read."""
    from security import is_production
    old = [k.strip() for k in os.getenv("ENCRYPTION_OLD_KEYS", "").split(",") if k.strip()]
    keys = [k for k in (os.getenv("ENCRYPTION_KEY"), os.getenv("JWT_SECRET"), *old) if k]
    if not keys and not is_production():
        keys = ["nimmi-local-dev-encryption"]  # development only; production always has JWT_SECRET
    if not keys:
        raise SecretError("Set ENCRYPTION_KEY on the server before storing secrets")
    return MultiFernet([_key(k) for k in dict.fromkeys(keys)])


def seal(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def unseal(token: str) -> str:
    try:
        return _fernet().decrypt((token or "").encode()).decode()
    except InvalidToken as e:
        raise SecretError("A stored secret can't be read. Was ENCRYPTION_KEY changed?") from e


class EncryptedText(TypeDecorator):
    """A text column stored encrypted at rest."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "" or (isinstance(value, str) and value.startswith(PREFIX)):
            return value
        return PREFIX + seal(str(value))

    def process_result_value(self, value, dialect):
        if not value or not value.startswith(PREFIX):
            return value  # empty, or saved before encryption was added
        try:
            return unseal(value[len(PREFIX):])
        except SecretError:
            logger.error("A stored secret couldn't be decrypted (ENCRYPTION_KEY changed?). Treating it as not set.")
            return None
