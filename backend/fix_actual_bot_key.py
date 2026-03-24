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
ACTUAL_BOT_ID = "894264ec-d748-4060-90a0-e5b60ba58eb5"

async def fix_actual_bot():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT bot_id, bot_name FROM bots WHERE bot_id = :id"), {"id": ACTUAL_BOT_ID})
        row = result.fetchone()
        if row:
            print(f"Update Bot: {row[1]} ({row[0]})")
            await conn.execute(text("UPDATE bots SET ai_api_key = :key WHERE bot_id = :id"), {"key": SYSTEM_API_KEY, "id": ACTUAL_BOT_ID})
            print(f"Successfully updated API key for bot {ACTUAL_BOT_ID}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_actual_bot())
