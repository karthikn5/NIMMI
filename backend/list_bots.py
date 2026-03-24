import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

async def list_bots():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT bot_id, bot_name, ai_api_key FROM bots"))
        rows = result.fetchall()
        for row in rows:
            print(f"ID: {row[0]}, Name: {row[1]}, API Key: {row[2][:8] if row[2] else 'None'}...")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(list_bots())
