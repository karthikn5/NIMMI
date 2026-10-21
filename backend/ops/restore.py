"""
Restore a backup made by ops/backup.py.

    python -m ops.restore nimmi-20261017-020000.backup           # into DATABASE_URL (or local SQLite)
    python -m ops.restore nimmi.backup --force                    # also into tables that already have rows;
                                                                  # rows whose id already exists are left alone

Needs the same ENCRYPTION_KEY (or JWT_SECRET) the backup was made with. Restore into a new, empty
database first (e.g. a fresh Supabase project), check it, then point DATABASE_URL at it.
"""
import argparse
import asyncio
import base64
from datetime import date, datetime

from sqlalchemy import Date, DateTime, func, insert, select


def _value(column, value):
    if value is None:
        return None
    if isinstance(value, dict) and "__bytes__" in value:
        return base64.b64decode(value["__bytes__"])
    if isinstance(column.type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date) and isinstance(value, str):
        return date.fromisoformat(value)
    return value


async def restore(blob: bytes, force: bool = False) -> dict:
    from database import Base, async_session, engine, init_db, is_sqlite
    from ops.backup import _load_models, open_backup

    _load_models()
    data = open_backup(blob)
    if data.get("format") != 1:
        raise RuntimeError("Unknown backup format")
    await init_db()
    counts = {}
    async with async_session() as db:
        for table in Base.metadata.sorted_tables:
            rows = data["tables"].get(table.name) or []
            if not rows:
                continue
            existing = (await db.execute(select(func.count()).select_from(table))).scalar_one()
            if existing and not force:
                raise RuntimeError(f"{table.name} already has {existing} rows. Restore into an empty database, or pass --force.")
            clean = [{c.name: _value(c, row.get(c.name)) for c in table.columns if c.name in row} for row in rows]
            if is_sqlite:
                stmt = insert(table).prefix_with("OR IGNORE")
            else:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(table).on_conflict_do_nothing()
            for i in range(0, len(clean), 500):
                await db.execute(stmt, clean[i:i + 500])
            counts[table.name] = len(clean)
        await db.commit()
    await engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a Nimmi database backup.")
    parser.add_argument("file")
    parser.add_argument("--force", action="store_true", help="restore into tables that already have rows")
    args = parser.parse_args()
    with open(args.file, "rb") as f:
        counts = asyncio.run(restore(f.read(), force=args.force))
    for name, n in counts.items():
        print(f"{name:28} {n}")
    print(f"Restored {sum(counts.values())} rows into {len(counts)} tables.")


if __name__ == "__main__":
    main()
