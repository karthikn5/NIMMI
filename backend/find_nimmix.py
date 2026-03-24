import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

async def find_nimmix():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT bot_id, bot_name FROM bots WHERE bot_name = 'NIMMIX'"))
        row = result.fetchone()
        if row:
            print(f"FOUND NIMMIX: ID={row[0]}")
        else:
            print("NIMMIX NOT FOUND by exact name.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(find_nimmix())
