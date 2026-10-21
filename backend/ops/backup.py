"""
Database backups, so customer data survives a bad deploy, a mistaken delete or an attack.

A backup is every table exported as JSON, gzipped and encrypted with the server's ENCRYPTION_KEY
(the same key that protects stored secrets, so keep a copy of it somewhere safe outside Railway).

  - Automatic: once a day the scheduler uploads one to the private Supabase Storage bucket
    "backups" and deletes copies older than BACKUP_KEEP_DAYS (default 30).
  - Manual:    python -m ops.backup --out nimmi.backup      (from the backend folder)
  - Restore:   python -m ops.restore nimmi.backup           (see ops/restore.py)

Supabase's own database backups (Pro plan) are the first line of defence; these are a second,
independent copy that also works on the free plan and can be restored into any database.
"""
import argparse
import asyncio
import base64
import gzip
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import Text, select, type_coerce

logger = logging.getLogger(__name__)

BUCKET = "backups"
FORMAT = 1
KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "30"))
_last_check = 0.0


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode()}
    return value


async def export_all() -> dict:
    """Every table, every row. Secrets stay encrypted exactly as stored."""
    from database import async_session, Base
    from secretbox import EncryptedText
    _load_models()

    tables = {}
    async with async_session() as db:
        for table in Base.metadata.sorted_tables:
            # Encrypted columns are read as stored (still encrypted), never decrypted into the file.
            cols = [type_coerce(c, Text).label(c.name) if isinstance(c.type, EncryptedText) else c for c in table.columns]
            rows = (await db.execute(select(*cols))).all()
            raw = []
            for row in rows:
                raw.append({c.name: _plain(v) for c, v in zip(table.columns, row)})
            tables[table.name] = raw
    return {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables}


def _load_models() -> None:
    """Register every table, under the same module name the running app uses."""
    import sys
    if "backend.models" in sys.modules or "models" in sys.modules:
        return
    import main  # noqa: F401  (sets up the `backend` package alias and imports the models)


def seal_backup(data: dict) -> bytes:
    from secretbox import _fernet
    return _fernet().encrypt(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))


def open_backup(blob: bytes) -> dict:
    from secretbox import _fernet
    return json.loads(gzip.decompress(_fernet().decrypt(blob)))


def _storage() -> Optional[tuple[str, dict]]:
    import supa
    url, key = os.getenv("SUPABASE_URL"), supa.service_key()
    return (url.rstrip("/"), supa.headers(key)) if url and key else None


async def _ensure_bucket(client: httpx.AsyncClient, url: str, headers: dict) -> None:
    resp = await client.get(f"{url}/storage/v1/bucket/{BUCKET}", headers=headers)
    if resp.status_code == 200:
        return
    created = await client.post(f"{url}/storage/v1/bucket", headers={**headers, "Content-Type": "application/json"},
                                json={"id": BUCKET, "name": BUCKET, "public": False})
    if created.status_code not in (200, 201, 409):
        raise RuntimeError(f"Couldn't create the backups bucket ({created.status_code})")


async def _list(client: httpx.AsyncClient, url: str, headers: dict) -> list[dict]:
    resp = await client.post(f"{url}/storage/v1/object/list/{BUCKET}", headers={**headers, "Content-Type": "application/json"},
                             json={"prefix": "", "limit": 1000, "sortBy": {"column": "name", "order": "desc"}})
    return resp.json() if resp.status_code == 200 else []


async def upload_backup() -> str:
    """Make a backup and store it in the private bucket. Returns its name."""
    where = _storage()
    if not where:
        raise RuntimeError("Backups need SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    url, headers = where
    blob = seal_backup(await export_all())
    name = f"nimmi-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.backup"
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_bucket(client, url, headers)
        resp = await client.post(f"{url}/storage/v1/object/{BUCKET}/{name}",
                                 headers={**headers, "Content-Type": "application/octet-stream"}, content=blob)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Backup upload failed ({resp.status_code}): {resp.text[:200]}")
        # Keep the last KEEP_DAYS days.
        cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
        old = [o["name"] for o in await _list(client, url, headers)
               if o.get("name", "").startswith("nimmi-") and _stamp(o["name"]) and _stamp(o["name"]) < cutoff]
        if old:
            await client.request("DELETE", f"{url}/storage/v1/object/{BUCKET}",
                                 headers={**headers, "Content-Type": "application/json"}, json={"prefixes": old})
    logger.info(f"Backup stored: {name} ({len(blob) // 1024} KB)")
    return name


def _stamp(name: str) -> Optional[datetime]:
    try:
        return datetime.strptime(name[len("nimmi-"):len("nimmi-") + 15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def maybe_backup() -> None:
    """Called by the scheduler loop: one backup a day, checked at most every 6 hours."""
    global _last_check
    if os.getenv("BACKUPS", "on").lower() == "off" or not _storage() or time.monotonic() - _last_check < 6 * 3600:
        return
    _last_check = time.monotonic()
    url, headers = _storage()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            latest = max((s for s in (_stamp(o.get("name", "")) for o in await _list(client, url, headers)) if s), default=None)
        if latest and datetime.now(timezone.utc) - latest < timedelta(hours=23):
            return
        await upload_backup()
    except Exception as e:  # never let a backup problem stop calls or emails
        logger.error(f"Daily backup failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the Nimmi database (encrypted).")
    parser.add_argument("--out", help="write the backup to this file instead of uploading it")
    args = parser.parse_args()
    if args.out:
        blob = seal_backup(asyncio.run(export_all()))
        with open(args.out, "wb") as f:
            f.write(blob)
        print(f"Wrote {args.out} ({len(blob) // 1024} KB)")
    else:
        print("Stored", asyncio.run(upload_backup()))


if __name__ == "__main__":
    main()
