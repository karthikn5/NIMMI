import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def verify_bot_exists():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        bot_id = "fd7068f9-431d-42b5-b677-66c3cd7126e0"
        result = await conn.execute(text("SELECT bot_id, user_id, bot_name FROM bots WHERE bot_id = :bid"), {"bid": bot_id})
        bot = result.fetchone()
        if bot:
            print(f"Bot found: {dict(bot._mapping)}")
        else:
            print(f"Bot {bot_id} NOT found in database.")
            
            # List all bots to see what's there
            result = await conn.execute(text("SELECT bot_id, bot_name FROM bots"))
            all_bots = result.fetchall()
            print(f"All bots in DB: {all_bots}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_bot_exists())
