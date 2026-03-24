
import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine
from models import Bot
from sqlalchemy.orm import sessionmaker

async def test_delete():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        # Try to delete the first bot found
        result = await session.execute(select(Bot))
        bot = result.scalars().first()
        if not bot:
            print("No bots found.")
            return
        
        print(f"Attempting to delete bot: {bot.bot_id} ({bot.bot_name})")
        try:
            await session.delete(bot)
            await session.commit()
            print("Successfully deleted bot.")
        except Exception as e:
            print(f"FAILED to delete bot: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(test_delete())
