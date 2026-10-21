"""
Where published sites' files live.

Files are stored once per site under their content hash ("<site_id>/<sha256>"), so a new deploy
uploads only what changed, unchanged files are shared between versions, and paths with any
characters are fine. Production uses a private Supabase Storage bucket; local development (and
only that) can use a folder on disk.
"""
import asyncio
import logging
import os
from typing import Iterable, Optional

import httpx

import supa
from security import is_production

logger = logging.getLogger(__name__)

BUCKET = "sites"
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_bucket_ready = False


def _supabase() -> Optional[tuple[str, str]]:
    url, key = os.getenv("SUPABASE_URL", "").rstrip("/"), supa.service_key()
    if url and key and "your-project" not in url:
        return url, key
    return None


def _local_dir() -> str:
    return os.getenv("SITES_DIR") or os.path.join(_HERE, "site_files")


def configured() -> bool:
    """Whether deploys can be stored: Supabase in production; a local folder is allowed only outside it."""
    return _supabase() is not None or not is_production()


def _key(site_id: str, sha: str) -> str:
    return f"{site_id}/{sha}"


async def _ensure_bucket(client: httpx.AsyncClient, url: str, key: str) -> None:
    global _bucket_ready
    if not _bucket_ready:
        _bucket_ready = await supa.ensure_bucket(client, url, key, BUCKET, public=False)


async def put_many(site_id: str, files: dict[str, bytes]) -> None:
    """Store {sha: bytes}. Raises if any file couldn't be stored (the deploy then fails, nothing half-published)."""
    if not files:
        return
    sb = _supabase()
    if sb is None:
        if is_production():
            raise RuntimeError("File storage isn't configured")
        folder = os.path.join(_local_dir(), site_id)
        os.makedirs(folder, exist_ok=True)
        for sha, data in files.items():
            with open(os.path.join(folder, sha), "wb") as f:
                f.write(data)
        return
    url, key = sb
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        await _ensure_bucket(client, url, key)

        async def one(sha: str, data: bytes):
            async with sem:
                for attempt in range(3):
                    r = await client.post(f"{url}/storage/v1/object/{BUCKET}/{_key(site_id, sha)}", content=data,
                                          headers={**supa.headers(key, "application/octet-stream"), "x-upsert": "true"})
                    if r.status_code in (200, 201):
                        return
                    await asyncio.sleep(1 + attempt)
                raise RuntimeError(f"Storage refused a file ({r.status_code})")
        await asyncio.gather(*(one(sha, data) for sha, data in files.items()))


async def get(site_id: str, sha: str) -> Optional[bytes]:
    sb = _supabase()
    if sb is None:
        path = os.path.join(_local_dir(), site_id, sha)
        if is_production() or not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()
    url, key = sb
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        r = await client.get(f"{url}/storage/v1/object/{BUCKET}/{_key(site_id, sha)}", headers=supa.headers(key))
    if r.status_code == 200:
        return r.content
    if r.status_code not in (400, 404):
        logger.warning(f"Site file {site_id}/{sha[:12]} unavailable: HTTP {r.status_code}")
    return None


async def delete_many(site_id: str, shas: Iterable[str]) -> None:
    """Best effort: an orphaned file costs a little storage, never correctness."""
    shas = list(shas)
    if not shas:
        return
    sb = _supabase()
    if sb is None:
        for sha in shas:
            try:
                os.remove(os.path.join(_local_dir(), site_id, sha))
            except OSError:
                pass
        return
    url, key = sb
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for start in range(0, len(shas), 500):
                await client.request("DELETE", f"{url}/storage/v1/object/{BUCKET}",
                                     headers=supa.headers(key, "application/json"),
                                     json={"prefixes": [_key(site_id, s) for s in shas[start:start + 500]]})
    except httpx.HTTPError as e:
        logger.warning(f"Removing old files of site {site_id} failed: {e}")
