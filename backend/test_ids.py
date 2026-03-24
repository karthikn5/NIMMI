import asyncio
from database import engine
from sqlalchemy import text

async def test():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT bot_id, bot_name, ai_api_key FROM bots"))
        for row in res.fetchall():
            print(f"ID: {row[0]}, Name: {row[1]}, Key: {'SET' if row[2] else 'EMPTY'}")

asyncio.run(test())
