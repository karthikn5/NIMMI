"""
Call recordings: a stereo WAV (left = caller, right = assistant), stored in a
private Supabase Storage bucket when configured, else under backend/storage.
Recordings are never public; the API hands out short-lived signed links.
"""
import asyncio
import logging
import os
import time
from array import array
from typing import Optional

import httpx

import supa

from voice.sarvam import pcm_to_wav

logger = logging.getLogger(__name__)

BUCKET = os.getenv("RECORDINGS_BUCKET", "call-recordings")
LOCAL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "recordings")


class Recorder:
    """Collects both sides of a call against one clock."""

    def __init__(self, sample_rate: int):
        self.rate = sample_rate
        self.t0 = time.monotonic()
        self.caller: list[tuple[int, bytes]] = []
        self.agent: list[tuple[int, bytes]] = []
        self._agent_cursor = 0  # agent audio queues behind earlier agent audio
        self._caller_cursor = 0

    def _now(self) -> int:
        return int((time.monotonic() - self.t0) * self.rate)

    def add_caller(self, pcm: bytes) -> None:
        # The caller side is one continuous stream, so append in order; arrival
        # times jitter and would otherwise make frames overwrite each other.
        self.caller.append((self._caller_cursor, pcm))
        self._caller_cursor += len(pcm) // 2

    def add_agent(self, pcm: bytes) -> None:
        start = max(self._now(), self._agent_cursor)
        self.agent.append((start, pcm))
        self._agent_cursor = start + len(pcm) // 2

    def cut_agent(self) -> None:
        """Barge-in: audio queued after now was never played."""
        now = self._now()
        kept = []
        for start, pcm in self.agent:
            if start >= now:
                continue
            played = (now - start) * 2
            kept.append((start, pcm[:played]))
        self.agent = kept
        self._agent_cursor = now

    def to_wav(self) -> bytes:
        def track(chunks):
            out = array("h")
            for start, pcm in chunks:
                samples = array("h")
                samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
                end = start + len(samples)
                if len(out) < end:
                    out.extend([0] * (end - len(out)))
                out[start:end] = samples
            return out

        left, right = track(self.caller), track(self.agent)
        n = max(len(left), len(right))
        left.extend([0] * (n - len(left)))
        right.extend([0] * (n - len(right)))
        stereo = array("h", [0]) * (2 * n)
        stereo[0::2], stereo[1::2] = left, right
        return pcm_to_wav(stereo.tobytes(), self.rate, channels=2)


def _supabase():
    url = os.getenv("SUPABASE_URL")
    key = supa.service_key()
    return (url.rstrip("/"), key) if url and key else (None, None)


async def save(call_id: str, wav: bytes) -> str:
    """Store a recording; returns its storage path ("supabase:..." or "local:...")."""
    url, key = _supabase()
    name = f"{call_id}.wav"
    if url:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{url}/storage/v1/object/{BUCKET}/{name}",
                    headers={**supa.headers(key, "audio/wav"), "x-upsert": "true"},
                    content=wav,
                )
                if resp.status_code not in (200, 201) and await supa.ensure_bucket(client, url, key, BUCKET, public=False):
                    resp = await client.post(
                        f"{url}/storage/v1/object/{BUCKET}/{name}",
                        headers={**supa.headers(key, "audio/wav"), "x-upsert": "true"},
                        content=wav,
                    )
            if resp.status_code in (200, 201):
                return f"supabase:{name}"
            logger.error(f"Recording upload failed ({resp.status_code}): {resp.text[:200]}; saving on the server disk")
        except Exception as e:
            logger.error(f"Recording upload error: {e}; saving on the server disk")
    os.makedirs(LOCAL_DIR, exist_ok=True)
    path = os.path.join(LOCAL_DIR, name)
    await asyncio.to_thread(lambda: open(path, "wb").write(wav))
    return f"local:{name}"


async def signed_url(path: str, ttl: int = 900) -> Optional[str]:
    """A temporary URL for a Supabase-stored recording."""
    url, key = _supabase()
    if not path.startswith("supabase:") or not url:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{url}/storage/v1/object/sign/{BUCKET}/{path.split(':', 1)[1]}",
            headers=supa.headers(key),
            json={"expiresIn": ttl},
        )
    if resp.status_code != 200:
        return None
    return f"{url}/storage/v1{resp.json().get('signedURL')}"


def local_path(path: str) -> Optional[str]:
    if not path.startswith("local:"):
        return None
    full = os.path.join(LOCAL_DIR, os.path.basename(path.split(":", 1)[1]))
    return full if os.path.exists(full) else None


async def delete(path: Optional[str]) -> None:
    if not path:
        return
    if path.startswith("local:"):
        full = local_path(path)
        if full:
            await asyncio.to_thread(os.remove, full)
        return
    url, key = _supabase()
    if url and path.startswith("supabase:"):
        async with httpx.AsyncClient(timeout=15) as client:
            await client.request("DELETE", f"{url}/storage/v1/object/{BUCKET}",
                                 headers=supa.headers(key),
                                 json={"prefixes": [path.split(":", 1)[1]]})
