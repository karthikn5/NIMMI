"""
Where WhatsApp files live: the business's Files (pamphlets, price lists…) and what customers send (voice notes, photos),
so the team can open them later (Meta deletes them after 30 days). A private Supabase bucket, read only through the
backend; the server's disk on a developer's machine or when storage isn't configured.
Stored paths are "supabase:<key>" or "local:<key>", keys "<workspace>/<id>.<ext>".
"""
import asyncio
import logging
import os
from typing import Optional

import httpx

import supa

logger = logging.getLogger(__name__)

BUCKET = os.getenv("WHATSAPP_BUCKET", "whatsapp-files")
LOCAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "whatsapp")


def _supabase() -> tuple[Optional[str], Optional[str]]:
    url, key = os.getenv("SUPABASE_URL"), supa.service_key()
    return (url.rstrip("/"), key) if url and key else (None, None)


def _local(key: str) -> str:
    owner, name = key.split("/", 1)
    return os.path.join(LOCAL_DIR, os.path.basename(owner), os.path.basename(name))


async def save(key: str, content: bytes, mime: str) -> str:
    url, skey = _supabase()
    if url:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                for attempt in range(2):
                    resp = await client.post(f"{url}/storage/v1/object/{BUCKET}/{key}",
                                             headers={**supa.headers(skey, mime), "x-upsert": "true"}, content=content)
                    if resp.status_code in (200, 201):
                        return f"supabase:{key}"
                    if attempt or not await supa.ensure_bucket(client, url, skey, BUCKET, public=False):
                        break
            logger.error(f"WhatsApp file upload failed ({resp.status_code}): {resp.text[:200]}; keeping it on the server")
        except Exception as e:
            logger.error(f"WhatsApp file upload error: {e}; keeping it on the server")
    path = _local(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    await asyncio.to_thread(lambda: open(path, "wb").write(content))
    return f"local:{key}"


async def load(stored: Optional[str]) -> Optional[bytes]:
    if not stored:
        return None
    where, key = stored.split(":", 1)
    if where == "local":
        path = _local(key)
        return await asyncio.to_thread(lambda: open(path, "rb").read()) if os.path.exists(path) else None
    url, skey = _supabase()
    if not url:
        return None
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(f"{url}/storage/v1/object/{BUCKET}/{key}", headers=supa.headers(skey))
    return resp.content if resp.status_code == 200 else None


async def delete(stored: Optional[str]) -> None:
    if not stored:
        return
    where, key = stored.split(":", 1)
    try:
        if where == "local":
            path = _local(key)
            if os.path.exists(path):
                await asyncio.to_thread(os.remove, path)
            return
        url, skey = _supabase()
        if url:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.request("DELETE", f"{url}/storage/v1/object/{BUCKET}", headers=supa.headers(skey),
                                     json={"prefixes": [key]})
    except Exception as e:
        logger.warning(f"Deleting WhatsApp file {key} failed: {e}")
