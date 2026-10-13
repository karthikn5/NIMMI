"""Encrypt secrets we must store and use later, such as a customer's Twilio auth token.

Uses ENCRYPTION_KEY (any long random string). Falls back to JWT_SECRET so existing servers
keep working, but set ENCRYPTION_KEY in production: rotating JWT_SECRET would otherwise make
stored secrets unreadable.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class SecretError(Exception):
    pass


def _fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY") or os.getenv("JWT_SECRET") or ""
    if not key:
        raise SecretError("Set ENCRYPTION_KEY on the server before connecting phone accounts")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def seal(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def unseal(token: str) -> str:
    try:
        return _fernet().decrypt((token or "").encode()).decode()
    except InvalidToken as e:
        raise SecretError("A stored secret can't be read. Was ENCRYPTION_KEY changed?") from e
