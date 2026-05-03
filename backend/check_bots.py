import asyncio
from database import get_db
from models import Bot
from sqlalchemy import select

async def check():
    async for db in get_db():
        result = await db.execute(select(Bot.bot_id, Bot.bot_name))
        bots = result.all()
        print(f"Total bots: {len(bots)}")
        for b in bots:
            print(f"- {b.bot_id}: {b.bot_name}")
        break

if __name__ == "__main__":
    asyncio.run(check())
