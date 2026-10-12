"""Supabase server-side access (Storage). Works with both key styles."""
import os
from typing import Optional


def service_key() -> Optional[str]:
    """Key for server-side writes to private buckets: the secret / service-role key."""
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None


def headers(key: str, content_type: Optional[str] = None) -> dict:
    """
    New keys (sb_secret_..., sb_publishable_...) go only in the `apikey` header;
    they aren't JWTs, so sending them as a Bearer token fails JWT checks.
    Legacy JWT keys (eyJ...) are also sent as Bearer, as before.
    """
    h = {"apikey": key}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    if content_type:
        h["Content-Type"] = content_type
    return h
