import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
# Trying direct connection bypass
DIRECT_URL = "postgresql+asyncpg://postgres.ouujdlxldeptgyjgntta:Karthikeyan%405@db.ouujdlxldeptgyjgntta.supabase.co:5432/postgres"

async def test():
    print(f"Connecting to DIRECT: {DIRECT_URL.split('@')[-1]}")
    engine = create_async_engine(DIRECT_URL)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            print("DIRECT Connection successful:", res.fetchone())
    except Exception as e:
        print("DIRECT Connection FAILED:", e)
    finally:
        await engine.dispose()

asyncio.run(test())
