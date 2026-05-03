import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SUB_ID = "84bd6dcf-7bc3-4f46-90f9-361410ae8173"
BOT_ID = "d55deb11-a8d0-45cb-945a-f61c9c11291f"

async def fix_data():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Direct update by ID
        await conn.execute(
            text("UPDATE subscriptions SET bot_id = :bot_id WHERE id = :sub_id"),
            {"bot_id": BOT_ID, "sub_id": SUB_ID}
        )
        print("Done")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_data())
