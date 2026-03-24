import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
import sqlite3

load_dotenv()

SUBSTRING = "894264ec"

async def check_postgres():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL: return
    if "asyncpg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        for table in ["bots", "users"]:
            result = await conn.execute(text(f"SELECT * FROM {table}"))
            rows = result.fetchall()
            for row in rows:
                if any(SUBSTRING in str(v) for v in row):
                    print(f"Postgres Match in {table}: {row}")
    await engine.dispose()

def check_sqlite():
    if os.path.exists("nimmi_local.db"):
        conn = sqlite3.connect("nimmi_local.db")
        cursor = conn.cursor()
        for table in ["bots", "users"]:
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                for row in rows:
                    if any(SUBSTRING in str(v) for v in row):
                        print(f"SQLite Match in {table}: {row}")
            except: pass
        conn.close()

if __name__ == "__main__":
    check_sqlite()
    asyncio.run(check_postgres())
