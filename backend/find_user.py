import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def find_user():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT user_id, bot_name FROM bots"))
        bots = [dict(row._mapping) for row in result]
        print(f"Bots in DB: {bots}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(find_user())
