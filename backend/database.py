import os
import sys

# The backend directory, so sibling modules import however the app is started.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

from security import is_production, local_dev, mask_url  # noqa: E402

# Use LOCAL_DEV=true to force SQLite (no DB credentials needed locally). Ignored in production.
LOCAL_DEV = local_dev()
DATABASE_URL = os.getenv("DATABASE_URL", "")

if is_production() and not DATABASE_URL:
    # Never fall back to a file inside the container in production: it is wiped on every deploy,
    # so the app would look healthy while silently losing every signup, chat and call.
    raise RuntimeError("DATABASE_URL is not set. Refusing to start in production without the real database.")

# SQLite only outside production: with LOCAL_DEV, an explicit SQLITE_PATH (tests, throwaway servers),
# or when no DATABASE_URL is set.
if not is_production() and (LOCAL_DEV or os.getenv("SQLITE_PATH") or not DATABASE_URL):
    # SQLite for local development - zero config needed
    # SQLITE_PATH lets tests and throwaway servers use their own database file
    DB_PATH = os.getenv("SQLITE_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "nimmi_local.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
    print(f"[DB] Using SQLite at {DB_PATH}")
else:
    # Ensure the URL uses the asyncpg driver for PostgreSQL
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    print(f"[DB] Using PostgreSQL URL: {mask_url(DATABASE_URL)}")

from sqlalchemy.pool import NullPool

is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # One connection per session (NullPool); opening a local file costs nothing. A single shared connection
    # (StaticPool) lets one session's rollback silently undo another session's writes.
    # `timeout` makes a writer wait for SQLite's lock instead of failing.
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )

    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_foreign_keys(dbapi_conn, _record):
        # SQLite ignores foreign keys unless asked; Postgres always enforces them (including ON DELETE
        # CASCADE). Turn them on so local runs and tests behave like production.
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # A small pool of open connections, reused across requests. Opening a connection to Supabase
    # (TLS + login over a long network path) measured ~2.4 s, against ~0.75 s for a query on an
    # open one; without a pool every request paid that. No pre-ping (it would add a round trip to
    # every request); connections are replaced after a few minutes instead.
    # Supabase's session pooler (port 5432) allows 15 clients in all, shared by every server process
    # (gunicorn runs 4), so the default is 2 kept open + 1 extra each: 12 at most. The transaction
    # pooler (port 6543) allows far more; raise DB_POOL_SIZE / DB_POOL_OVERFLOW there.
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=int(os.getenv("DB_POOL_SIZE", "2")),
        max_overflow=int(os.getenv("DB_POOL_OVERFLOW", "1")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SEC", "240")),
        pool_timeout=30,
        connect_args={
            "ssl": "require",
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
            "command_timeout": 60,
            "server_settings": {
                "jit": "off",
                "response_timeout": "60"
            }
        }
    )

# Create async session factory
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# Dependency to get database session
async def get_db():
    async with async_session() as session:
        yield session

async def init_db():
    try:
        from backend.models import Base
    except ImportError:
        from models import Base
    async with engine.begin() as conn:
        # Check if tables exist by querying information_schema
        # This is more robust than create_all in some environments
        try:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_add_missing_columns, Base.metadata)
            await conn.run_sync(_add_missing_indexes, Base.metadata)
            await conn.run_sync(_relax_not_null, "contacts", "e164")  # a chat lead with only an email is a contact too
            await conn.run_sync(_encrypt_legacy_secrets)
            print("Database tables created/verified.")
        except Exception as e:
            print(f"Error creating tables: {e}")
    if not is_sqlite:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(_close_public_api)
        except Exception as e:
            print(f"[DB] Could not verify table access rules: {e}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_reseal_secrets, Base.metadata)
    except Exception as e:
        print(f"[DB] Could not re-encrypt stored secrets: {e}")


def _close_public_api(sync_conn) -> None:
    """
    Supabase publishes every table in `public` over its REST API to anyone holding the publishable
    key (which ships in the website). Nimmi reads its data only through this backend, so keep row
    level security on for every table (new ones included) and give the API roles no access.
    The backend connects as the table owner, which RLS doesn't restrict.
    """
    from sqlalchemy import text

    roles = {r[0] for r in sync_conn.execute(text("select rolname from pg_roles where rolname in ('anon', 'authenticated')"))}
    tables = [r[0] for r in sync_conn.execute(text(
        "select tablename from pg_tables where schemaname = 'public' and not rowsecurity"))]
    for table in tables:
        sync_conn.execute(text(f'alter table public."{table}" enable row level security'))
        print(f"[DB] Turned on row level security for {table}")
    if roles:
        who = ", ".join(sorted(roles))
        for stmt in (f"revoke all on all tables in schema public from {who}",
                     f"revoke all on all sequences in schema public from {who}",
                     f"alter default privileges in schema public revoke all on tables from {who}",
                     f"alter default privileges in schema public revoke all on sequences from {who}"):
            sync_conn.execute(text(stmt))


def _add_missing_columns(sync_conn, metadata) -> None:
    """
    create_all() doesn't add new columns to tables that already exist. Add any
    missing *nullable* columns (safe on SQLite and Postgres; no data is touched).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or not column.nullable:
                continue
            ddl_type = column.type.compile(dialect=sync_conn.dialect)
            sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))
            print(f"[DB] Added column {table.name}.{column.name}")


def _add_missing_indexes(sync_conn, metadata) -> None:
    """Indexes the models declare on columns added after their table existed (create_all skips existing tables)."""
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {i["name"] for i in inspector.get_indexes(table.name)}
        columns = {c["name"] for c in inspector.get_columns(table.name)}
        for index in table.indexes:
            if index.name in present or not all(c.name in columns for c in index.columns):
                continue
            index.create(sync_conn, checkfirst=True)
            print(f"[DB] Added index {index.name}")


def _relax_not_null(sync_conn, table: str, column: str) -> None:
    """Let a column that used to be required be empty. Postgres alters it in place; SQLite (local development) can't,
    so the table is rebuilt with the same definition minus NOT NULL, its rows and indexes copied over."""
    import re
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    if table not in inspector.get_table_names():
        return
    columns = {c["name"]: c for c in inspector.get_columns(table)}
    if column not in columns or columns[column]["nullable"]:
        return
    if sync_conn.dialect.name == "postgresql":
        sync_conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL'))
    elif sync_conn.dialect.name == "sqlite":
        ddl = sync_conn.execute(text("select sql from sqlite_master where type = 'table' and name = :t"), {"t": table}).scalar()
        relaxed, found = re.subn(rf'(^\s*"?{column}"?\s+[^,\n]*?)\s+NOT NULL', r"\1", ddl, count=1, flags=re.MULTILINE)
        renamed, named = re.subn(rf'^CREATE TABLE "?{table}"?', f'CREATE TABLE "{table}__rebuild"', relaxed, count=1)
        if not (found and named):
            print(f"[DB] Couldn't make {table}.{column} optional: unexpected table definition")
            return
        indexes = [sql for (sql,) in sync_conn.execute(text(
            "select sql from sqlite_master where type = 'index' and tbl_name = :t and sql is not null"), {"t": table})]
        names = ", ".join(f'"{c}"' for c in columns)
        sync_conn.execute(text(renamed))
        sync_conn.execute(text(f'INSERT INTO "{table}__rebuild" ({names}) SELECT {names} FROM "{table}"'))
        sync_conn.execute(text(f'DROP TABLE "{table}"'))
        sync_conn.execute(text(f'ALTER TABLE "{table}__rebuild" RENAME TO "{table}"'))
        for sql in indexes:
            sync_conn.execute(text(sql))
    else:
        return
    print(f"[DB] {table}.{column} may now be empty")


# Where secrets are sealed outside EncryptedText columns: whole values, and values inside JSON ("enc:v1:...").
SEALED_TEXT = [("telephony_accounts", "secrets"), ("twilio_keys", "secret")]
SEALED_JSON = [("voice_agents", "functions"), ("voice_agents", "inbound")]


def _reseal_secrets(sync_conn, metadata) -> None:
    """A key was replaced (ENCRYPTION_OLD_KEYS is set): every stored secret still under an old key is encrypted again
    with the current one. It runs at each start while the old keys are listed; once the log says nothing was left and
    nothing unreadable, they can be removed (rotating after Railway's Oct 2026 incident)."""
    import os
    from sqlalchemy import select, text
    import secretbox

    if not os.getenv("ENCRYPTION_OLD_KEYS", "").strip():
        return
    changed, unreadable = 0, 0

    def again(token: str) -> str:
        nonlocal changed, unreadable
        try:
            fresh = secretbox.reseal(token)
        except secretbox.SecretError:
            unreadable += 1
            return token
        changed += fresh != token
        return fresh

    def inside(value):
        if isinstance(value, dict):
            return {k: inside(v) for k, v in value.items()}
        if isinstance(value, list):
            return [inside(v) for v in value]
        if isinstance(value, str) and value.startswith(secretbox.PREFIX):
            return secretbox.PREFIX + again(value[len(secretbox.PREFIX):])
        return value

    def raw(table, column: str, prefix: str) -> None:
        pk = list(table.primary_key.columns)[0].name
        for key, value in sync_conn.execute(text(f'select "{pk}", "{column}" from "{table.name}" where "{column}" like :p'),
                                            {"p": prefix + "%"}).all():
            fresh = prefix + again(value[len(prefix):])
            if fresh != value:
                sync_conn.execute(text(f'update "{table.name}" set "{column}" = :v where "{pk}" = :k'), {"v": fresh, "k": key})

    for table in metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, secretbox.EncryptedText):
                raw(table, column.name, secretbox.PREFIX)
    for name, column in SEALED_TEXT:
        raw(metadata.tables[name], column, "")
    for name, column in SEALED_JSON:
        table = metadata.tables[name]
        pk = list(table.primary_key.columns)[0]
        for key, value in sync_conn.execute(select(pk, table.c[column]).where(table.c[column].is_not(None))).all():
            fresh = inside(value)
            if fresh != value:
                sync_conn.execute(table.update().where(pk == key).values({column: fresh}))
    print(f"[DB] Secrets moved to the current key: {changed}; unreadable with any key: {unreadable}")


# Columns stored with secretbox.EncryptedText: (table, primary key, columns).
SECRET_COLUMNS = [
    ("bots", "bot_id", ["ai_api_key"]),
    ("integration_settings", "user_id", ["webhook_secret", "leadsquared_access_key", "leadsquared_secret_key", "whatsapp_access_token"]),
]


def _encrypt_legacy_secrets(sync_conn) -> None:
    """Encrypt secrets saved in plain text before encryption existed. Safe to run on every start."""
    from sqlalchemy import text
    from secretbox import PREFIX, seal

    for table, pk, columns in SECRET_COLUMNS:
        for col in columns:
            rows = sync_conn.execute(text(
                f"""select "{pk}", "{col}" from "{table}" where "{col}" is not null and "{col}" <> '' and "{col}" not like :p"""
            ), {"p": PREFIX + "%"}).all()
            for key, value in rows:
                sync_conn.execute(text(f'update "{table}" set "{col}" = :v where "{pk}" = :k'), {"v": PREFIX + seal(value), "k": key})
            if rows:
                print(f"[DB] Encrypted {len(rows)} stored secret(s) in {table}.{col}")
