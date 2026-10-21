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


async def ensure_bucket(client, url: str, key: str, name: str, public: bool) -> bool:
    """Create a storage bucket if it doesn't exist (needs the service key). True if it exists now."""
    hdrs = headers(key)
    if (await client.get(f"{url}/storage/v1/bucket/{name}", headers=hdrs)).status_code == 200:
        return True
    resp = await client.post(f"{url}/storage/v1/bucket", headers={**hdrs, "Content-Type": "application/json"},
                             json={"id": name, "name": name, "public": public})
    return resp.status_code in (200, 201, 409)
