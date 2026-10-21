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
    # One connection per session (NullPool), like Postgres. A single shared connection
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
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        poolclass=NullPool,
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
