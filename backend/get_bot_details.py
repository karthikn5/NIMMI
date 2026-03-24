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

async def check_bot(bot_id):
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT * FROM bots WHERE bot_id = :id"), {"id": bot_id})
        columns = result.keys()
        row = result.fetchone()
        if row:
            data = dict(zip(columns, row))
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(f"Bot {bot_id} NOT found")
    await engine.dispose()

if __name__ == "__main__":
    import sys
    bot_id = sys.argv[1] if len(sys.argv) > 1 else "894264ec-d748-4060-90a0-e5b50ba58eb5"
    asyncio.run(check_bot(bot_id))
