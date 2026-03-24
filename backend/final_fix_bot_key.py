import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

SYSTEM_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_ID = "894264ec-d748-4060-90a0-e5b50ba58eb5"

async def fix_bot():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Check if it exists for sure now
        result = await conn.execute(text("SELECT bot_id, bot_name FROM bots WHERE bot_id = :id"), {"id": BOT_ID})
        row = result.fetchone()
        if row:
            print(f"Found bot: {row[1]} ({row[0]})")
            await conn.execute(text("UPDATE bots SET ai_api_key = :key WHERE bot_id = :id"), {"key": SYSTEM_API_KEY, "id": BOT_ID})
            print(f"Successfully updated API key for bot {BOT_ID}")
        else:
            print(f"FAILED: Bot {BOT_ID} still not found in exact match. Trying substring update...")
            await conn.execute(text("UPDATE bots SET ai_api_key = :key WHERE bot_id LIKE :id_part"), {"key": SYSTEM_API_KEY, "id_part": f"%{BOT_ID[:8]}%"})
            print(f"Attempted substring update for ID part {BOT_ID[:8]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_bot())
