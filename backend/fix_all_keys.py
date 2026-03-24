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

async def fix_all_bots():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT bot_id, bot_name, ai_api_key FROM bots"))
        rows = result.fetchall()
        print(f"Updating {len(rows)} bots...")
        for row in rows:
            bot_id, name, current_key = row
            print(f"Updating Bot: {name} ({bot_id})")
            await conn.execute(text("UPDATE bots SET ai_api_key = :key WHERE bot_id = :id"), {"key": SYSTEM_API_KEY, "id": bot_id})
        print("All bots updated.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_all_bots())
