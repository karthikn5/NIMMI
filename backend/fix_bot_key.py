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

SYSTEM_API_KEY = os.getenv("GEMINI_API_KEY")

async def update_bot(bot_id):
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Check current key
        result = await conn.execute(text("SELECT ai_api_key FROM bots WHERE bot_id = :id"), {"id": bot_id})
        row = result.fetchone()
        if row:
            print(f"Current key for {bot_id}: {row[0]}")
            # Update to system key
            await conn.execute(text("UPDATE bots SET ai_api_key = :key WHERE bot_id = :id"), {"key": SYSTEM_API_KEY, "id": bot_id})
            print(f"Updated bot {bot_id} with system API key: {SYSTEM_API_KEY[:8]}...")
        else:
            print(f"Bot {bot_id} NOT found")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_bot("894264ec-d748-4060-90a0-e5b50ba58eb5"))
