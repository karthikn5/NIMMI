import sys
import os
# Absolute path to backend directory to solve virtual environment import issues
sys.path.append(r'c:\Users\karth\.gemini\antigravity\scratch\nimmi-ai\backend')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Use LOCAL_DEV=true to force SQLite (no DB credentials needed locally)
LOCAL_DEV = os.getenv("LOCAL_DEV", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "")

if LOCAL_DEV or not DATABASE_URL:
    # SQLite for local development - zero config needed
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nimmi_local.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
    print(f"[DB] Using SQLite at {DB_PATH}")
else:
    # Ensure the URL uses the asyncpg driver for PostgreSQL
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    print(f"[DB] Using PostgreSQL URL: {DATABASE_URL}")

from sqlalchemy.pool import NullPool, StaticPool

is_sqlite = DATABASE_URL.startswith("sqlite")

if is_sqlite:
    # SQLite needs StaticPool and check_same_thread=False
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    from backend.models import Base
    async with engine.begin() as conn:
        # Check if tables exist by querying information_schema
        # This is more robust than create_all in some environments
        try:
            await conn.run_sync(Base.metadata.create_all)
            print("Database tables created/verified.")
        except Exception as e:
            print(f"Error creating tables: {e}")
