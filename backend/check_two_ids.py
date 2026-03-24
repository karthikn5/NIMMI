import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

ID_SCREENSHOT = "894264ec-d748-4060-90a0-e5b50ba58eb5"
ID_NAME_SEARCH = "894264ec-d748-4060-90a0-e5b60ba58eb5"

async def check_ids():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        for bot_id in [ID_SCREENSHOT, ID_NAME_SEARCH]:
            result = await conn.execute(text("SELECT bot_id, bot_name, ai_api_key FROM bots WHERE bot_id = :id"), {"id": bot_id})
            row = result.fetchone()
            if row:
                print(f"FOUND: ID={row[0]} Name='{row[1]}' Key={row[2][:8] if row[2] else 'None'}...")
            else:
                print(f"NOT FOUND: {bot_id}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_ids())
